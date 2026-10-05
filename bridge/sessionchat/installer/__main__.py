import sys

from .boundaries import Boundaries
from .catalogue import DEFAULT_LANGUAGE
from .main import main
from .options import language_of
from .roles import built_in_roles

arguments = sys.argv[1:]
boundaries = Boundaries.real(language_of(arguments, DEFAULT_LANGUAGE))
raise SystemExit(main(arguments, boundaries, built_in_roles()))
