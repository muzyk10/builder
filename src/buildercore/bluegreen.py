"""Performs blue-green actions over a load-balanced stack.

The nodes inside a stack are divided into two groups: blue and green. Actions are performed separately on the two groups while they are detached from the load balancer. Obviously, requires a load balancer.

nodes_params is a data structure (dictionary) .
TODO: make nodes_params a named tuple"""
import logging
from .core import boto_elb_conn, parallel_work
from .utils import ensure, call_while

LOG = logging.getLogger(__name__)

class BlueGreenConcurrency():
    def __init__(self, region='us-east-1'):
        self.conn = boto_elb_conn(region)

    def __call__(self, single_node_work, nodes_params):
        elb_name = self.find_load_balancer(nodes_params['stackname'])
        blue, green = self.divide_by_color(nodes_params)

        LOG.info("Blue phase on %s: %s", elb_name, self._instance_ids(blue))
        self.deregister(elb_name, blue)
        self.wait_deregistered_all(elb_name, blue)
        parallel_work(single_node_work, blue)

        # this is the window of time in which old and new servers overlap
        self.register(elb_name, blue)
        self.wait_registered_any(elb_name, blue)

        LOG.info("Green phase on %s: %s", elb_name, self._instance_ids(blue))
        self.deregister(elb_name, green)
        self.wait_deregistered_all(elb_name, green)
        parallel_work(single_node_work, green)
        self.register(elb_name, green)

        self.wait_registered_all(elb_name, nodes_params)

    def find_load_balancer(self, stackname):
        names = [lb['LoadBalancerName'] for lb in self.conn.describe_load_balancers()['LoadBalancerDescriptions']]
        ensure(len(names) >= 1, "No load balancers found")
        tags = self.conn.describe_tags(LoadBalancerNames=names)['TagDescriptions']
        balancers = [lb['LoadBalancerName'] for lb in tags if {'Key': 'Cluster', 'Value': stackname} in lb['Tags']]
        ensure(len(balancers) == 1, "Expected to find exactly 1 load balancer, but found %s", balancers)
        return balancers[0]

    def divide_by_color(self, nodes_params):
        is_blue = lambda node: node % 2 == 1
        is_green = lambda node: node % 2 == 0

        def subset(is_subset):
            subset = nodes_params.copy()
            subset['nodes'] = {id: node for (id, node) in nodes_params['nodes'].items() if is_subset(node)}
            subset['public_ips'] = {id: ip for (id, ip) in nodes_params['public_ips'].items() if id in subset['nodes'].keys()}
            return subset
        return subset(is_blue), subset(is_green)

    def register(self, elb_name, nodes_params):
        LOG.info("Registering on %s: %s", elb_name, self._instance_ids(nodes_params))
        self.conn.register_instances_with_load_balancer(
            LoadBalancerName=elb_name,
            Instances=self._instances(nodes_params),
        )

    def deregister(self, elb_name, nodes_params):
        LOG.info("Deregistering on %s: %s", elb_name, self._instance_ids(nodes_params))
        self.conn.deregister_instances_from_load_balancer(
            LoadBalancerName=elb_name,
            Instances=self._instances(nodes_params),
        )

    def wait_registered_any(self, elb_name, nodes_params):
        LOG.info("Waiting for registration of any on %s: %s", elb_name, self._instance_ids(nodes_params))
        # TODO: reimplement with call_while because polling interval cannot be customized
        waiter = self.conn.get_waiter('any_instance_in_service')
        waiter.wait(LoadBalancerName=elb_name, Instances=self._instances(nodes_params))

    def wait_registered_all(self, elb_name, nodes_params):
        LOG.info("Waiting for registration of all on %s: %s", elb_name, self._instance_ids(nodes_params))
        # TODO: reimplement with call_while because polling interval cannot be customized
        waiter = self.conn.get_waiter('instance_in_service')
        waiter.wait(LoadBalancerName=elb_name, Instances=self._instances(nodes_params))

    def wait_deregistered_all(self, elb_name, nodes_params):
        LOG.info("Waiting for deregistration of all on %s: %s", elb_name, self._instance_ids(nodes_params))

        def condition():
            health = self.conn.describe_instance_health(
                LoadBalancerName=elb_name,
                Instances=self._instances(nodes_params)
            )['InstanceStates']
            registered = self._registered(health)
            LOG.info("InService: %s", registered)
            return True in registered.values()

        call_while(condition)

    def _registered(self, health):
        return {result['InstanceId']: result['State'] == 'InService' for result in health}

    def _instances(self, nodes_params):
        return [{'InstanceId': instance_id} for instance_id in self._instance_ids(nodes_params)]

    def _instance_ids(self, nodes_params):
        return nodes_params['nodes'].keys()
