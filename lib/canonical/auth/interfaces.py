from zope.interface import Interface, Attribute
from persistent import IPersistent


class IAuthApplication(Interface):
    """ Interface for AuthApplication """
    def __getitem__(name):
        """ The __getitem__ method used to traversing """

class IPasswordReminders(IPersistent):
    """ Interface for PasswordReminders"""
    def append(personId, code):
        """ Append a request in PasswordReminders """

    def retrieve(code):
        """ Retrieves the personId by code from PasswordReminders"""
        
class IpasswordChangeApp(Interface):
    """ Interface for passwdChangeApp """
    code = Attribute("The transaction code")
