from collections import OrderedDict
import json
import os
import re
import shutil
import yaml
from os.path import exists, join
from mock import patch, MagicMock
# pylint: disable-msg=import-error
from unittest2 import TestCase
from . import base
from buildercore import cfngen, terraform


class TestTerraformTemplate(TestCase):
    def test_resource_creation(self):
        template = terraform.TerraformTemplate()
        template.populate_resource('google_bigquery_dataset', 'my_dataset', block={
            'location': 'EU',
        })
        self.assertEqual(
            template.to_dict(),
            {
                'resource': OrderedDict([
                    ('google_bigquery_dataset', OrderedDict([
                        ('my_dataset', {'location': 'EU'}),
                    ])),
                ])
            }
        )

    def test_nested_resource_creation(self):
        template = terraform.TerraformTemplate()
        template.populate_resource('google_bigquery_dataset', 'my_dataset', key='labels', block={
            'project': 'journal',
        })
        self.assertEqual(
            template.to_dict(),
            {
                'resource': OrderedDict([
                    ('google_bigquery_dataset', OrderedDict([
                        ('my_dataset', OrderedDict([
                            ('labels', {'project': 'journal'}),
                        ])),
                    ])),
                ])
            }
        )

    def test_nested_resource_creation_if_already_existing(self):
        template = terraform.TerraformTemplate()
        template.populate_resource('google_bigquery_dataset', 'my_dataset', key='labels', block={
            'project': 'journal',
        })
        overwrite = lambda: template.populate_resource('google_bigquery_dataset', 'my_dataset', key='labels', block={'project': 'lax', })
        self.assertRaises(terraform.TerraformTemplateError, overwrite)

    def test_resource_creation_in_multiple_phases(self):
        template = terraform.TerraformTemplate()
        template.populate_resource('google_bigquery_dataset', 'my_dataset', block={
            'location': 'EU',
        })
        template.populate_resource('google_bigquery_dataset', 'my_dataset', key='labels', block={
            'project': 'journal',
        })
        self.assertEqual(
            template.to_dict(),
            {
                'resource': OrderedDict([
                    ('google_bigquery_dataset', OrderedDict([
                        ('my_dataset', OrderedDict([
                            ('location', 'EU'),
                            ('labels', {'project': 'journal'}),
                        ])),
                    ])),
                ])
            }
        )

    def test_resource_elements_creation(self):
        template = terraform.TerraformTemplate()
        template.populate_resource_element('google_bigquery_dataset', 'my_dataset', key='access', block={
            'role': 'reader',
        })
        template.populate_resource_element('google_bigquery_dataset', 'my_dataset', key='access', block={
            'role': 'writer',
        })
        self.assertEqual(
            template.to_dict(),
            {
                'resource': OrderedDict([
                    ('google_bigquery_dataset', OrderedDict([
                        ('my_dataset', OrderedDict([
                            ('access', [
                                {'role': 'reader'},
                                {'role': 'writer'},
                            ]),
                        ])),
                    ])),
                ])
            }
        )

    def test_data_creation(self):
        template = terraform.TerraformTemplate()
        template.populate_data('vault_generic_secret', 'my_credentials', block={
            'username': 'mickey',
            'password': 'mouse',
        })
        self.assertEqual(
            template.to_dict(),
            {
                'data': OrderedDict([
                    ('vault_generic_secret', OrderedDict([
                        ('my_credentials', OrderedDict([
                            ('username', 'mickey'),
                            ('password', 'mouse'),
                        ])),
                    ])),
                ])
            }
        )

    def test_data_creation_same_type(self):
        template = terraform.TerraformTemplate()
        template.populate_data('vault_generic_secret', 'my_credentials', block={
            'username': 'mickey',
            'password': 'mouse',
        })
        template.populate_data('vault_generic_secret', 'my_ssh_key', block={
            'private': '-----BEGIN RSA PRIVATE KEY-----',
        })
        self.assertEqual(
            template.to_dict(),
            {
                'data': OrderedDict([
                    ('vault_generic_secret', OrderedDict([
                        ('my_credentials', {
                            'username': 'mickey',
                            'password': 'mouse',
                        }),
                        ('my_ssh_key', {
                            'private': '-----BEGIN RSA PRIVATE KEY-----',
                        }),
                    ])),
                ])
            }
        )

    def test_data_creation_different_type(self):
        template = terraform.TerraformTemplate()
        template.populate_data('vault_generic_secret', 'my_credentials', block={
            'username': 'mickey',
            'password': 'mouse',
        })
        template.populate_data('http', 'my_page', block={
            'url': 'https://example.com',
        })
        self.assertEqual(
            template.to_dict(),
            {
                'data': OrderedDict([
                    ('vault_generic_secret', OrderedDict([
                        ('my_credentials', {
                            'username': 'mickey',
                            'password': 'mouse',
                        }),
                    ])),
                    ('http', OrderedDict([
                        ('my_page', {
                            'url': 'https://example.com',
                        }),
                    ])),
                ])
            }
        )

    def test_data_creation_if_already_existing(self):
        template = terraform.TerraformTemplate()
        template.populate_data('vault_generic_secret', 'my_credentials', block={
            'username': 'mickey',
        })
        overwrite = lambda: template.populate_data('vault_generic_secret', 'my_credentials', block={'username': 'minnie'})
        self.assertRaises(terraform.TerraformTemplateError, overwrite)


class TestBuildercoreTerraform(base.BaseCase):
    def setUp(self):
        self.project_config = join(self.fixtures_dir, 'projects', "dummy-project.yaml")
        os.environ['LOGNAME'] = 'my_user'
        self.environment = base.generate_environment_name()
        test_directory = join(terraform.TERRAFORM_DIR, 'dummy1--%s' % self.environment)
        if exists(test_directory):
            shutil.rmtree(test_directory)

    def tearDown(self):
        del os.environ['LOGNAME']

    @patch('buildercore.terraform.Terraform')
    def test_init_providers(self, Terraform):
        terraform_binary = MagicMock()
        Terraform.return_value = terraform_binary
        stackname = 'project-with-fastly-minimal--%s' % self.environment
        context = cfngen.build_context('project-with-fastly-minimal', stackname=stackname)
        terraform.init(stackname, context)
        terraform_binary.init.assert_called_once()
        for _, configuration in self._load_terraform_file(stackname, 'providers').get('provider').items():
            self.assertIn('version', configuration)

    @patch('buildercore.terraform.Terraform')
    def test_fastly_provider_reads_api_key_from_vault(self, Terraform):
        terraform_binary = MagicMock()
        Terraform.return_value = terraform_binary
        stackname = 'project-with-fastly-minimal--%s' % self.environment
        context = cfngen.build_context('project-with-fastly-minimal', stackname=stackname)
        terraform.init(stackname, context)
        providers_file = self._load_terraform_file(stackname, 'providers')
        self.assertEqual(
            providers_file.get('provider').get('fastly').get('api_key'),
            '${data.vault_generic_secret.fastly.data["api_key"]}'
        )
        self.assertEqual(
            providers_file.get('data').get('vault_generic_secret').get('fastly'),
            {
                'path': 'secret/builder/apikey/fastly',
            }
        )

    @patch('buildercore.terraform.Terraform')
    def test_delta(self, Terraform):
        terraform_binary = MagicMock()
        Terraform.return_value = terraform_binary
        terraform_binary.plan.return_value = (0, 'Plan output: ...', '')
        stackname = 'project-with-fastly-minimal--%s' % self.environment
        context = cfngen.build_context('project-with-fastly-minimal', stackname=stackname)
        terraform.init(stackname, context)
        delta = terraform.generate_delta(context)
        self.assertEqual(delta, terraform.TerraformDelta('Plan output: ...'))

    def test_fastly_template_minimal(self):
        extra = {
            'stackname': 'project-with-fastly-minimal--%s' % self.environment,
        }
        context = cfngen.build_context('project-with-fastly-minimal', **extra)
        terraform_template = terraform.render(context)
        template = self._parse_template(terraform_template)
        self.assertEqual(
            {
                'resource': {
                    'fastly_service_v1': {
                        # must be unique but only in a certain context like this, use some constants
                        'fastly-cdn': {
                            'name': 'project-with-fastly-minimal--%s' % self.environment,
                            'domain': [{
                                'name': '%s--cdn-of-www.example.org' % self.environment,
                            }],
                            'backend': [{
                                'address': '%s--www.example.org' % self.environment,
                                'name': 'project-with-fastly-minimal--%s' % self.environment,
                                'port': 443,
                                'use_ssl': True,
                                'ssl_cert_hostname': '%s--www.example.org' % self.environment,
                                'ssl_sni_hostname': '%s--www.example.org' % self.environment,
                                'ssl_check_cert': True,
                            }],
                            'default_ttl': 3600,
                            'request_setting': [
                                {
                                    'name': 'force-ssl',
                                    'force_ssl': True,
                                    'timer_support': True,
                                    'xff': 'leave',
                                }
                            ],
                            'gzip': {
                                'name': 'default',
                                'content_types': ['application/javascript', 'application/json',
                                                  'application/vnd.ms-fontobject',
                                                  'application/x-font-opentype',
                                                  'application/x-font-truetype',
                                                  'application/x-font-ttf',
                                                  'application/x-javascript', 'application/xml',
                                                  'font/eot', 'font/opentype', 'font/otf',
                                                  'image/svg+xml', 'image/vnd.microsoft.icon',
                                                  'text/css', 'text/html', 'text/javascript',
                                                  'text/plain', 'text/xml'],
                                'extensions': ['css', 'eot', 'html', 'ico', 'js', 'json', 'otf',
                                               'ttf'],
                            },
                            'force_destroy': True,
                            'vcl': [],
                        }
                    }
                },
            },
            template
        )

    def test_fastly_template_complex(self):
        extra = {
            'stackname': 'project-with-fastly-complex--%s' % self.environment,
        }
        context = cfngen.build_context('project-with-fastly-complex', **extra)
        terraform_template = terraform.render(context)
        template = self._parse_template(terraform_template)
        self.assertEqual(
            {
                'data': {
                    'http': {
                        'error-page-404': {
                            'url': 'https://example.com/404.html'
                        },
                        'error-page-503': {
                            'url': 'https://example.com/503.html'
                        },
                        'error-page-4xx': {
                            'url': 'https://example.com/4xx.html'
                        },
                        'error-page-5xx': {
                            'url': 'https://example.com/5xx.html'
                        },
                    },
                    'template_file': {
                        'error-page-vcl-503': {
                            'template': '${file("error-page.vcl.tpl")}',
                            'vars': {
                                'test': 'obj.status == 503',
                                'synthetic_response': '${data.http.error-page-503.body}',
                            },
                        },
                        'error-page-vcl-404': {
                            'template': '${file("error-page.vcl.tpl")}',
                            'vars': {
                                'test': 'obj.status == 404',
                                'synthetic_response': '${data.http.error-page-404.body}',
                            },
                        },
                        'error-page-vcl-4xx': {
                            'template': '${file("error-page.vcl.tpl")}',
                            'vars': {
                                'test': 'obj.status >= 400 && obj.status <= 499',
                                'synthetic_response': '${data.http.error-page-4xx.body}',
                            },
                        },
                        'error-page-vcl-5xx': {
                            'template': '${file("error-page.vcl.tpl")}',
                            'vars': {
                                'test': 'obj.status >= 500 && obj.status <= 599',
                                'synthetic_response': '${data.http.error-page-5xx.body}',
                            },
                        },
                        'journal-submit': {
                            'template': '${file("journal-submit.vcl.tpl")}',
                            'vars': {
                                'percentage': 10,
                                'referer': '^https://xpub\.example\.com/',
                                'xpub_uri': 'https://xpub.example.com/login',
                            },
                        },
                    },
                },
                'resource': {
                    'fastly_service_v1': {
                        # must be unique but only in a certain context like this, use some constants
                        'fastly-cdn': {
                            'name': 'project-with-fastly-complex--%s' % self.environment,
                            'domain': [
                                {
                                    'name': '%s--cdn1-of-www.example.org' % self.environment,
                                },
                                {
                                    'name': '%s--cdn2-of-www.example.org' % self.environment,
                                },
                                {
                                    'name': 'example.org'
                                },
                                {
                                    'name': 'anotherdomain.org'
                                },
                                {
                                    'name': 'future.example.org'
                                },
                            ],
                            'backend': [
                                {
                                    'address': 'default.example.org',
                                    'name': 'default',
                                    'port': 443,
                                    'use_ssl': True,
                                    'ssl_cert_hostname': 'default.example.org',
                                    'ssl_sni_hostname': 'default.example.org',
                                    'ssl_check_cert': True,
                                    'healthcheck': 'default',
                                },
                                {
                                    'address': '%s-special.example.org' % self.environment,
                                    'name': 'articles',
                                    'port': 443,
                                    'use_ssl': True,
                                    'ssl_cert_hostname': '%s-special.example.org' % self.environment,
                                    'ssl_sni_hostname': '%s-special.example.org' % self.environment,
                                    'ssl_check_cert': True,
                                    'request_condition': 'backend-articles-condition',
                                    'healthcheck': 'default',
                                    'shield': 'amsterdam-nl',
                                },
                                {
                                    'address': '%s-special2.example.org' % self.environment,
                                    'name': 'articles2',
                                    'port': 443,
                                    'use_ssl': True,
                                    'ssl_cert_hostname': '%s-special2.example.org' % self.environment,
                                    'ssl_sni_hostname': '%s-special2.example.org' % self.environment,
                                    'ssl_check_cert': True,
                                    'request_condition': 'backend-articles2-condition',
                                    'healthcheck': 'default',
                                    'shield': 'dca-dc-us',
                                },
                                {
                                    'address': '%s-special3.example.org' % self.environment,
                                    'name': 'articles3',
                                    'port': 443,
                                    'use_ssl': True,
                                    'ssl_cert_hostname': '%s-special3.example.org' % self.environment,
                                    'ssl_sni_hostname': '%s-special3.example.org' % self.environment,
                                    'ssl_check_cert': True,
                                    'request_condition': 'backend-articles3-condition',
                                    'healthcheck': 'default',
                                    'shield': 'dca-dc-us',
                                },
                            ],
                            'request_setting': [
                                {
                                    'name': 'force-ssl',
                                    'force_ssl': True,
                                    'timer_support': True,
                                    'xff': 'leave',
                                },
                                {
                                    'name': 'backend-articles-request-settings',
                                    'timer_support': True,
                                    'xff': 'leave',
                                    'request_condition': 'backend-articles-condition',
                                },
                                {
                                    'name': 'backend-articles2-request-settings',
                                    'timer_support': True,
                                    'xff': 'leave',
                                    'request_condition': 'backend-articles2-condition',
                                },
                                {
                                    'name': 'backend-articles3-request-settings',
                                    'timer_support': True,
                                    'xff': 'leave',
                                    'request_condition': 'backend-articles3-condition',
                                },
                            ],
                            'default_ttl': 86400,
                            'gzip': {
                                'name': 'default',
                                'content_types': ['application/javascript', 'application/json',
                                                  'application/vnd.ms-fontobject',
                                                  'application/x-font-opentype',
                                                  'application/x-font-truetype',
                                                  'application/x-font-ttf',
                                                  'application/x-javascript', 'application/xml',
                                                  'font/eot', 'font/opentype', 'font/otf',
                                                  'image/svg+xml', 'image/vnd.microsoft.icon',
                                                  'text/css', 'text/html', 'text/javascript',
                                                  'text/plain', 'text/xml'],
                                'extensions': ['css', 'eot', 'html', 'ico', 'js', 'json', 'otf',
                                               'ttf'],
                            },
                            'healthcheck': {
                                'host': '%s--www.example.org' % self.environment,
                                'name': 'default',
                                'path': '/ping-fastly',
                                'check_interval': 30000,
                                'timeout': 10000,
                            },
                            'condition': [
                                {
                                    'name': 'backend-articles-condition',
                                    'statement': 'req.url ~ "^/articles"',
                                    'type': 'REQUEST',
                                },
                                {
                                    'name': 'backend-articles2-condition',
                                    'statement': 'req.url ~ "^/articles2"',
                                    'type': 'REQUEST',
                                },
                                {
                                    'name': 'backend-articles3-condition',
                                    'statement': 'req.url ~ "^/articles3"',
                                    'type': 'REQUEST',
                                },
                                {
                                    'name': 'condition-surrogate-article-id',
                                    'statement': 'req.url ~ "^/articles/(\\d+)/(.+)$"',
                                    'type': 'CACHE',
                                },
                            ],
                            'vcl': [
                                {
                                    'name': 'gzip-by-content-type-suffix',
                                    'content': '${file("gzip-by-content-type-suffix.vcl")}',
                                },
                                {
                                    'name': 'journal-submit',
                                    'content': '${data.template_file.journal-submit.rendered}',
                                },
                                {
                                    'name': 'error-page-vcl-503',
                                    'content': '${data.template_file.error-page-vcl-503.rendered}',
                                },
                                {
                                    'name': 'error-page-vcl-404',
                                    'content': '${data.template_file.error-page-vcl-404.rendered}',
                                },
                                {
                                    'name': 'error-page-vcl-4xx',
                                    'content': '${data.template_file.error-page-vcl-4xx.rendered}',
                                },
                                {
                                    'name': 'error-page-vcl-5xx',
                                    'content': '${data.template_file.error-page-vcl-5xx.rendered}',
                                },
                                {
                                    'name': 'main',
                                    'content': '${file("main.vcl")}',
                                    'main': True,
                                },
                            ],
                            'header': [
                                {
                                    'name': 'surrogate-keys article-id',
                                    'type': 'cache',
                                    'action': 'set',
                                    'source': 'regsub(req.url, "^/articles/(\\d+)/(.+)$", "article/\\1")',
                                    'destination': 'http.surrogate-key',
                                    'ignore_if_set': True,
                                    'cache_condition': 'condition-surrogate-article-id',
                                },
                            ],
                            'force_destroy': True,
                        }
                    }
                },
            },
            template
        )

    def test_fastly_template_shield(self):
        extra = {
            'stackname': 'project-with-fastly-shield--%s' % self.environment,
        }
        context = cfngen.build_context('project-with-fastly-shield', **extra)
        terraform_template = terraform.render(context)
        template = self._parse_template(terraform_template)
        service = template['resource']['fastly_service_v1']['fastly-cdn']
        self.assertEqual(service['backend'][0].get('shield'), 'dca-dc-us')
        self.assertIn('domain', service)

    def test_fastly_template_shield_pop(self):
        extra = {
            'stackname': 'project-with-fastly-shield-pop--%s' % self.environment,
        }
        context = cfngen.build_context('project-with-fastly-shield-pop', **extra)
        terraform_template = terraform.render(context)
        template = self._parse_template(terraform_template)
        service = template['resource']['fastly_service_v1']['fastly-cdn']
        self.assertEqual(service['backend'][0].get('shield'), 'london-uk')
        self.assertIn('domain', service)

    def test_fastly_template_shield_aws_region(self):
        base.switch_in_test_settings(['src/tests/fixtures/additional-projects/'])
        extra = {
            'stackname': 'project-with-fastly-shield-aws-region--%s' % self.environment,
        }
        context = cfngen.build_context('project-with-fastly-shield-aws-region', **extra)
        terraform_template = terraform.render(context)
        template = self._parse_template(terraform_template)
        service = template['resource']['fastly_service_v1']['fastly-cdn']
        self.assertEqual(service['backend'][0].get('shield'), 'frankfurt-de')

    def test_fastly_template_gcs_logging(self):
        extra = {
            'stackname': 'project-with-fastly-gcs--%s' % self.environment,
        }
        context = cfngen.build_context('project-with-fastly-gcs', **extra)
        terraform_template = terraform.render(context)
        template = self._parse_template(terraform_template)
        service = template['resource']['fastly_service_v1']['fastly-cdn']
        self.assertIn('gcslogging', service)
        self.assertEqual(service['gcslogging'].get('name'), 'default')
        self.assertEqual(service['gcslogging'].get('bucket_name'), 'my-bucket')
        self.assertEqual(service['gcslogging'].get('path'), 'my-project/')
        self.assertEqual(service['gcslogging'].get('period'), 1800)
        self.assertEqual(service['gcslogging'].get('message_type'), 'blank')
        self.assertEqual(service['gcslogging'].get('email'), '${data.vault_generic_secret.fastly-gcs-logging.data["email"]}')
        self.assertEqual(service['gcslogging'].get('secret_key'), '${data.vault_generic_secret.fastly-gcs-logging.data["secret_key"]}')

        log_format = service['gcslogging'].get('format')
        # the non-rendered log_format is not even valid JSON
        self.assertIsNotNone(log_format)
        self.assertRegex(log_format, "\{.*\}")

        data = template['data']['vault_generic_secret']['fastly-gcs-logging']
        self.assertEqual(data, {'path': 'secret/builder/apikey/fastly-gcs-logging'})

    def test_fastly_template_bigquery_logging(self):
        extra = {
            'stackname': 'project-with-fastly-bigquery--%s' % self.environment,
        }
        context = cfngen.build_context('project-with-fastly-bigquery', **extra)
        terraform_template = terraform.render(context)
        template = self._parse_template(terraform_template)
        service = template['resource']['fastly_service_v1']['fastly-cdn']
        self.assertIn('bigquerylogging', service)
        self.assertEqual(service['bigquerylogging'].get('name'), 'bigquery')
        self.assertEqual(service['bigquerylogging'].get('project_id'), 'my-project')
        self.assertEqual(service['bigquerylogging'].get('dataset'), 'my_dataset')
        self.assertEqual(service['bigquerylogging'].get('table'), 'my_table')
        self.assertEqual(service['bigquerylogging'].get('email'), '${data.vault_generic_secret.fastly-gcp-logging.data["email"]}')
        self.assertEqual(service['bigquerylogging'].get('secret_key'), '${data.vault_generic_secret.fastly-gcp-logging.data["secret_key"]}')

        log_format = service['bigquerylogging'].get('format')
        # the non-rendered log_format is not even valid JSON
        self.assertIsNotNone(log_format)
        self.assertRegex(log_format, "\{.*\}")

        data = template['data']['vault_generic_secret']['fastly-gcp-logging']
        self.assertEqual(data, {'path': 'secret/builder/apikey/fastly-gcp-logging'})

    def test_gcp_template(self):
        extra = {
            'stackname': 'project-on-gcp--%s' % self.environment,
        }
        context = cfngen.build_context('project-on-gcp', **extra)
        terraform_template = terraform.render(context)
        template = self._parse_template(terraform_template)
        bucket = template['resource']['google_storage_bucket']['widgets-%s' % self.environment]
        self.assertEqual(bucket, {
            'name': 'widgets-%s' % self.environment,
            'location': 'us-east4',
            'storage_class': 'REGIONAL',
            'project': 'elife-something',
        })

    def test_bigquery_datasets_only(self):
        extra = {
            'stackname': 'project-with-bigquery-datasets-only--%s' % self.environment,
        }
        context = cfngen.build_context('project-with-bigquery-datasets-only', **extra)
        terraform_template = terraform.render(context)
        template = self._parse_template(terraform_template)
        dataset = template['resource']['google_bigquery_dataset']['my_dataset_%s' % self.environment]
        self.assertEqual(dataset, {
            'dataset_id': 'my_dataset_%s' % self.environment,
            'project': 'elife-something',
        })

        self.assertNotIn('google_bigquery_table', template['resource'])

    def test_bigquery_full_template(self):
        extra = {
            'stackname': 'project-with-bigquery--%s' % self.environment,
        }
        context = cfngen.build_context('project-with-bigquery', **extra)
        terraform_template = terraform.render(context)
        template = self._parse_template(terraform_template)
        dataset = template['resource']['google_bigquery_dataset']['my_dataset_%s' % self.environment]
        self.assertEqual(dataset, {
            'dataset_id': 'my_dataset_%s' % self.environment,
            'project': 'elife-something',
        })

        table = template['resource']['google_bigquery_table']['my_dataset_%s_widgets' % self.environment]
        self.assertEqual(table, {
            'dataset_id': '${google_bigquery_dataset.my_dataset_%s.dataset_id}' % self.environment,
            'table_id': 'widgets',
            'project': 'elife-something',
            'schema': '${file("key-value.json")}',
        })

    def test_bigquery_remote_paths(self):
        "remote paths require terraform to fetch and load the files, which requires another entry in the 'data' list"
        pname = 'project-with-bigquery-remote-schemas'
        iid = pname + '--%s' % self.environment
        context = cfngen.build_context(pname, stackname=iid)
        terraform_template = json.loads(terraform.render(context))

        self.assertEqual(
            terraform_template,
            {
                'resource': {
                    'google_bigquery_dataset': {
                        'my_dataset_%s' % self.environment: {
                            'project': 'elife-something',
                            'dataset_id': 'my_dataset_%s' % self.environment
                        }
                    },
                    'google_bigquery_table': {
                        'my_dataset_%s_remote' % self.environment: {
                            'project': 'elife-something',
                            'dataset_id': '${google_bigquery_dataset.my_dataset_%s.dataset_id}' % self.environment,
                            'table_id': 'remote',
                            'schema': '${data.http.my_dataset_%s_remote.body}' % self.environment,
                        },
                        'my_dataset_%s_remote_github' % self.environment: {
                            'project': 'elife-something',
                            'dataset_id': '${google_bigquery_dataset.my_dataset_%s.dataset_id}' % self.environment,
                            'table_id': 'remote_github',
                            'schema': '${data.http.my_dataset_%s_remote_github.body}' % self.environment,
                        },
                        'my_dataset_%s_local' % self.environment: {
                            'project': 'elife-something',
                            'dataset_id': '${google_bigquery_dataset.my_dataset_%s.dataset_id}' % self.environment,
                            'table_id': 'local',
                            'schema': '${file("key-value.json")}'
                        }
                    }
                },
                'data': {
                    'http': {
                        'my_dataset_%s_remote' % self.environment: {
                            'url': 'https://example.org/schemas/remote.json'
                        },
                        'my_dataset_%s_remote_github' % self.environment: {
                            'url': 'https://raw.githubusercontent.com/myrepo/something.json',
                            'request_headers': {
                                'Authorization': 'token ${data.vault_generic_secret.github.data["token"]}',
                            },
                        },
                    },
                    'vault_generic_secret': {
                        'github': {'path': 'secret/builder/apikey/github'}
                    },
                }
            }
        )

    def test_eks_cluster(self):
        pname = 'project-with-eks'
        iid = pname + '--%s' % self.environment
        context = cfngen.build_context(pname, stackname=iid)
        terraform_template = json.loads(terraform.render(context))

        self.assertIn('resource', terraform_template)
        self.assertIn('aws_eks_cluster', terraform_template['resource'])
        self.assertIn('main', terraform_template['resource']['aws_eks_cluster'])
        self.assertEqual(
            terraform_template['resource']['aws_eks_cluster']['main'],
            {
                'name': 'project-with-eks--%s' % self.environment,
                'role_arn': '${aws_iam_role.eks_master.arn}',
                'vpc_config': {
                    'security_group_ids': ["${aws_security_group.kubernetes--%s.id}" % self.environment],
                    'subnet_ids': ['subnet-a1a1a1a1', 'subnet-b2b2b2b2'],
                },
                'depends_on': [
                    "aws_iam_role_policy_attachment.kubernetes--demo--AmazonEKSClusterPolicy",
                    "aws_iam_role_policy_attachment.kubernetes--demo--AmazonEKSServicePolicy",
                ]
            }
        )

        self.assertIn('aws_iam_role', terraform_template['resource'])
        self.assertIn('eks_master', terraform_template['resource']['aws_iam_role'])
        self.assertEqual(
            terraform_template['resource']['aws_iam_role']['eks_master']['name'],
            'kubernetes--%s--AmazonEKSMasterRole' % self.environment
        )
        self.assertEqual(
            json.loads(terraform_template['resource']['aws_iam_role']['eks_master']['assume_role_policy']),
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {
                            "Service": "eks.amazonaws.com"
                        },
                        "Action": "sts:AssumeRole"
                    }
                ]
            }
        )


#resource "aws_iam_role_policy_attachment" "kubernetes--demo--AmazonEKSClusterPolicy" {
#  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
#  role       = "${aws_iam_role.kubernetes--demo.name}"
#}
#
#resource "aws_iam_role_policy_attachment" "kubernetes--demo--AmazonEKSServicePolicy" {
#  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSServicePolicy"
#  role       = "${aws_iam_role.kubernetes--demo.name}"
#}

    def test_sanity_of_rendered_log_format(self):
        def _render_log_format_with_dummy_template():
            return re.sub(
                r"%\{.+\}(V|t)",
                '42',
                terraform.FASTLY_LOG_FORMAT,
            )
        log_sample = json.loads(_render_log_format_with_dummy_template())
        self.assertEqual(log_sample.get('object_hits'), 42)
        self.assertEqual(log_sample.get('geo_city'), '42')

    def test_generated_template_file_storage(self):
        contents = '{"key":"value"}'
        filename = terraform.write_template('dummy1--%s' % self.environment, contents)
        self.assertEqual(filename, '.cfn/terraform/dummy1--%s/generated.tf.json' % self.environment)
        self.assertEqual(terraform.read_template('dummy1--%s' % self.environment), contents)

    def _parse_template(self, terraform_template):
        """use yaml module to load JSON to avoid large u'foo' vs 'foo' string diffs
        https://stackoverflow.com/a/16373377/91590"""
        return yaml.safe_load(terraform_template)

    def _load_terraform_file(self, stackname, filename):
        with open(join(terraform.TERRAFORM_DIR, stackname, '%s.tf.json' % filename), 'r') as fp:
            return self._parse_template(fp.read())
