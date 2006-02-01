# Copyright 2004-2005 Canonical Ltd.  All rights reserved.
#
# This is a Twisted application config file.  To run, use:
#     twistd -noy sftp.tac
# or similar.  Refer to the twistd(1) man page for details.

import os

from twisted.cred import portal
from twisted.conch.ssh import keys
from twisted.application import service, internet

from canonical.authserver.client.twistedclient import TwistedAuthServer

from supermirrorsftp import sftponly

authserverURL = 'http://localhost:8999/v2/'
# mkdir keys; cd keys; ssh-keygen -t rsa -f ssh_host_key_rsa
keydir = os.environ.get('SUPERMIRROR_KEYDIR', os.path.join(os.getcwd(),'keys'))
hostPublicKey = keys.getPublicKeyString(
    data=open(os.path.join(keydir, 'ssh_host_key_rsa.pub'), 'rb').read()
)
hostPrivateKey = keys.getPrivateKeyObject(
    data=open(os.path.join(keydir, 'ssh_host_key_rsa'), 'rb').read()
)

# Configure the authentication
homedirs = os.environ.get('SUPERMIRROR_HOMEDIRS', '/tmp')
authserver = TwistedAuthServer(authserverURL)
portal = portal.Portal(sftponly.Realm(homedirs, authserver))
portal.registerChecker(sftponly.PublicKeyFromLaunchpadChecker(authserver))
sftpfactory = sftponly.Factory(hostPublicKey, hostPrivateKey)
sftpfactory.portal = portal

# Configure it to listen on a port
application = service.Application('sftponly')
portNo = int(os.environ.get('SUPERMIRROR_PORT', '5022'))
internet.TCPServer(portNo, sftpfactory).setServiceParent(application)

