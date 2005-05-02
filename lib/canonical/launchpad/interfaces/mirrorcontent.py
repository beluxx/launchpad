# Zope schema imports
from zope.schema import Int
from zope.interface import Interface
from zope.i18nmessageid import MessageIDFactory
_ = MessageIDFactory('launchpad')

#
#
#

class IMirrorContent(Interface):
    mirror = Int(title=_("Mirror"), required=True,
                 description=_("The Mirror where this content is."))
    distroarchrelease = Int(title=_("Distroarchrelease"), required=True,
                        description=_("The content's Distro Arch Release"))
    component = Int(title=_("Component"), required=True,
                        description=_("The content's Component"))
