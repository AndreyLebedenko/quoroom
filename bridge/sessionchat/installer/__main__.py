import sys

from .boundaries import Boundaries
from .main import main
from .roles import built_in_roles

raise SystemExit(main(sys.argv[1:], Boundaries.real(), built_in_roles()))
