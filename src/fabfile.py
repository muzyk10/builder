import os

# pylint: disable=unused-wildcard-import,unused-import,wildcard-import

SRC_DIR = os.path.dirname(os.path.abspath(__file__)) # elife-builder/src/

# once called 'THIS_DIR', now deprecated as confusing.
PROJECT_DIR = os.path.dirname(SRC_DIR)    # elife-builder/

from cfn import *

import aws
import metrics
import tasks
import master
import askmaster
import buildvars
import project
from deploy import switch_revision_update_instance
from lifecycle import start, stop, stop_if_running_for, update_dns
import masterless
import fixtures
