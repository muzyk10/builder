# from . import core # DONT import core. this project module should be relatively independent
from buildercore import utils, config
from buildercore.decorators import osissue
from kids.cache import cache
from . import files

import copy

import logging
from functools import reduce
LOG = logging.getLogger(__name__)

#
# project data utilities
#

def set_project_alt(pdata, env, altkey):
    "non-destructive update of given project data with the specified alternative configuration."
    assert env in ['vagrant', 'aws', 'gcp'], "'env' must be either 'vagrant' or 'aws'"
    env_key = env + '-alt'
    assert altkey in pdata[env_key], "project has no alternative config %r. Available: %s" % (altkey, list(pdata[env_key].keys()))
    pdata_copy = copy.deepcopy(pdata) # don't modify the data given to us
    pdata_copy[env] = pdata[env_key][altkey]
    return pdata_copy

def find_project(project_location_triple):
    "given a triple of (protocol, hostname, path) returns a map of {org => project data}"
    plt = project_location_triple
    assert utils.iterable(plt), "given triple must be a collection of three values"
    assert len(project_location_triple) == 3, "triple must contain three values. got: %r" % project_location_triple
    protocol, hostname, path = plt
    fnmap = {
        #'file': OrgFileProjects,
        'file': files.projects_from_file,
        #'ssh': RemoteBuilderProjects,
        #'https': RemoteBuilderProjects,
    }
    if not protocol in fnmap.keys():
        LOG.info("unhandled protocol %r for %r" % (protocol, plt))
        return {}  # OrderedDict({})
    return fnmap[protocol](path, hostname)

def raw_project_map():
    "returns an unprocessed list of maps of project data"
    project_locations_list = config.app()['project-locations']

    struct = {files.project_file_name(path): files.all_projects(path) for _, _, path in project_locations_list}
    utils.ensure(len(struct) == 1, "`raw_project_map` doesn't support multiple project files")
    return struct.values()[0]

@cache
def project_map(project_locations_list=None):
    """returns a single map of all projects and their data"""
    def merge(orderedDict1, orderedDict2):
        orderedDict1.update(orderedDict2)
        return orderedDict1

    project_locations_list = config.app()['project-locations']
    # ll: {'dummy-project1': {'lax': {'aws': ..., 'vagrant': ..., 'salt': ...}, 'metrics': {...}},
    #      'dummy-project2': {'example': {}}}
    data = map(find_project, project_locations_list)
    opm = reduce(merge, data)
    # ll: [{'lax': {'aws': ..., 'vagrant': ..., 'salt': ...}, 'metrics': {...}}], {'example': {}}]
    data = opm.values()
    # ll: {'lax': {...}, 'metrics': {...}, 'example': {...}}

    return reduce(merge, data)

def project_list(project_locations_list=None):
    "returns a single list of projects, ignoring organization and project data"
    return list(project_map(project_locations_list).keys())

def project_data(pname, project_locations_list=None):
    "returns the data for a single project."
    data = project_map(project_locations_list)
    try:
        return data[pname]
    except KeyError:
        raise ValueError("unknown project %r, known projects %r" % (pname, data.keys()))

#
#
#

def filtered_projects(filterfn, *args, **kwargs):
    "returns a dict of projects filtered by given filterfn)"
    return utils.dictfilter(filterfn, project_map(*args, **kwargs))

def branch_deployable_projects(*args, **kwargs):
    "returns a pair of (defaults, dict of projects with a repo)"
    return filtered_projects(lambda pname, pdata: 'repo' in pdata, *args, **kwargs)

def projects_with_formulas(*args, **kwargs):
    return filtered_projects(lambda pname, pdata: pdata.get('formula-repo'), *args, **kwargs)

def aws_projects(*args, **kwargs):
    return filtered_projects(lambda pname, pdata: 'aws' in pdata, *args, **kwargs)

def ec2_projects(*args, **kwargs):
    return filtered_projects(lambda pname, pdata: pdata.get('aws', {}).get('ec2'), *args, **kwargs)

#
#
#

def transformed_projects(mapfn, *args, **kwargs):
    return utils.dictmap(mapfn, project_map(*args, **kwargs))

def project_formulas():
    return transformed_projects(lambda _, pdata: [pdata.get('formula-repo')] + pdata.get('formula-dependencies', []))

#
#
#

def known_formulas():
    "a simple list of all known project formulas (excluding the private-repo)"
    lst = utils.unique(utils.shallow_flatten(project_formulas().values()))
    if None in lst:
        lst.remove(None)
    return lst
