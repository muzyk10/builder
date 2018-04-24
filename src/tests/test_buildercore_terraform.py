import os
import yaml
from os.path import join
from . import base
from buildercore import cfngen, terraform

class TestBuildercoreTerraform(base.BaseCase):
    def setUp(self):
        self.project_config = join(self.fixtures_dir, 'projects', "dummy-project.yaml")
        os.environ['LOGNAME'] = 'my_user'

    def tearDown(self):
        del os.environ['LOGNAME']

    def test_fastly_template_minimal(self):
        extra = {
            'stackname': 'project-with-fastly-minimal--prod',
        }
        context = cfngen.build_context('project-with-fastly-minimal', **extra)
        terraform_template = terraform.render(context)
        data = self._parse_template(terraform_template)
        self.assertEqual(
            {
                'resource': {
                    'fastly_service_v1': {
                        # must be unique but only in a certain context like this, use some constants
                        'fastly-cdn': {
                            'name': 'project-with-fastly-minimal--prod',
                            'domain': [{
                                'name': 'prod--cdn-of-www.example.org'
                            }],
                            'backend': {
                                'address': 'prod--www.example.org',
                                'name': 'project-with-fastly-minimal--prod',
                                'port': 443,
                                'use_ssl': True,
                                'ssl_cert_hostname': 'prod--www.example.org',
                                'ssl_check_cert': True,
                            },
                            'request_setting': {
                                'name': 'default',
                                'force_ssl': True,
                                'timer_support': True,
                                'xff': 'leave',
                            },
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
                            'force_destroy': True
                        }
                    }
                },
            },
            data
        )

    def test_fastly_template_complex(self):
        extra = {
            'stackname': 'project-with-fastly-complex--prod',
        }
        context = cfngen.build_context('project-with-fastly-complex', **extra)
        terraform_template = terraform.render(context)
        data = self._parse_template(terraform_template)
        self.assertEqual(
            {
                'resource': {
                    'fastly_service_v1': {
                        # must be unique but only in a certain context like this, use some constants
                        'fastly-cdn': {
                            'name': 'project-with-fastly-complex--prod',
                            'domain': [
                                {
                                    'name': 'prod--cdn1-of-www.example.org'
                                },
                                {
                                    'name': 'prod--cdn2-of-www.example.org'
                                },
                                {
                                    'name': 'future.example.org'
                                },
                            ],
                            'backend': {
                                'address': 'prod--www.example.org',
                                'name': 'project-with-fastly-complex--prod',
                                'port': 443,
                                'use_ssl': True,
                                'ssl_cert_hostname': 'prod--www.example.org',
                                'ssl_check_cert': True
                            },
                            'request_setting': {
                                'name': 'default',
                                'force_ssl': True,
                                'timer_support': True,
                                'xff': 'leave',
                            },
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
                            'force_destroy': True
                        }
                    }
                },
            },
            data
        )

    def test_write_template(self):
        contents = '{"key":"value"}'
        terraform.write_template('dummy1--test', contents)
        self.assertEqual(terraform.read_template('dummy1--test'), contents)

    def _parse_template(self, terraform_template):
        """use yaml module to load JSON to avoid large u'foo' vs 'foo' string diffs
        https://stackoverflow.com/a/16373377/91590"""
        return yaml.safe_load(terraform_template)
