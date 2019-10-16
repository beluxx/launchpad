from zope.interface import (
    Interface
)
from zope.schema import (
    Int,
    Text,
    )

from lp import _


class IOCIRecipeName(Interface):

    id = Int(title=_("OCI Recipe Name ID"),
             required=True,
             readonly=True
             )

    name = Text(title=_("Name of recipe"))


class IOCIRecipeNameSet(Interface):

    def __getitem__(name):
        """Retrieve a ocirecipename by name."""

    def getByName(name):
        """Return a ocirecipename by its name.

        If the ocirecipename can't be found a NoSuchRecipeName will be
        raised.
        """

    def getAll():
        """return an iselectresults representing all package names"""

    def new(name):
        """Create a new oci recipe name."""
