from fabric.api import task, local
from buildercore import project, utils as core_utils, core, cfngen
from buildercore.utils import ensure
from decorators import requires_project, echo_output
import utils

@task
@requires_project
@echo_output
def data(pname, output_format=None):
    "given a project name, returns the fully realized project description data."
    formatters = {
        'json': core_utils.json_dumps,
        'yaml': core_utils.yaml_dumps,
        # None: core_utils.remove_ordereddict
        None: lambda v: v
    }
    ensure(output_format in formatters.keys(), "unknown output format %r" % output_format)
    formatter = formatters.get(output_format)
    return formatter(project.project_data(pname))

@task
@requires_project
@echo_output
def context(pname, output_format=None):
    formatters = {
        'json': core_utils.json_dumps,
        'yaml': core_utils.yaml_dumps,
        # None: core_utils.remove_ordereddict
        None: lambda v: v
    }
    ensure(output_format in formatters.keys(), "unknown output format %r" % output_format)
    formatter = formatters.get(output_format)
    return formatter(cfngen.build_context(pname, stackname=core.mk_stackname(pname, "test")))

@task
def new():
    "creates a new project formula"
    pname = utils.uin('project name')
    #assert pname not in project.project_list(), "that project name already exists"
    local('./scripts/new-project.sh %s' % pname)
