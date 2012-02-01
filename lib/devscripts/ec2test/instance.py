# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Code to represent a single machine instance in EC2."""

__metaclass__ = type
__all__ = [
    'EC2Instance',
    ]

import code
from datetime import datetime
import errno
import glob
import os
import select
import socket
import subprocess
import sys
import time
import traceback

from bzrlib.errors import BzrCommandError
import paramiko

from devscripts.ec2test.session import EC2SessionName


DEFAULT_INSTANCE_TYPE = 'm2.xlarge'
DEFAULT_REGION = 'us-east-1'
AVAILABLE_INSTANCE_TYPES = (
    'm1.large', 'm1.xlarge', 'm2.xlarge', 'm2.2xlarge', 'm2.4xlarge',
    'c1.xlarge', 'cc1.4xlarge', 'cc1.8xlarge')


class AcceptAllPolicy:
    """We accept all unknown host key."""

    def missing_host_key(self, client, hostname, key):
        # Normally the console output is supposed to contain the Host key but
        # it doesn't seem to be the case here, so we trust that the host we
        # are connecting to is the correct one.
        pass


def get_user_key():
    """Get a SSH key from the agent.  Raise an error if no keys were found.

    This key will be used to let the user log in (as $USER) to the instance.
    """
    agent = paramiko.Agent()
    keys = agent.get_keys()
    if len(keys) == 0:
        raise BzrCommandError(
            'You must have an ssh agent running with keys installed that '
            'will allow the script to access Launchpad and get your '
            'branch.\n')

    # XXX mars 2010-05-07 bug=577118
    # Popping the first key off of the stack can create problems if the person
    # has more than one key in their ssh-agent, but alas, we have no good way
    # to detect the right key to use.  See bug 577118 for a workaround.
    return keys[0]


# Commands to run to turn a blank image into one usable for the rest of the
# ec2 functionality.  They come in two parts, one set that need to be run as
# root and another that should be run as the 'ec2test' user.
# Note that the sources from http://us.ec2.archive.ubuntu.com/ubuntu/ are per
# instructions described in http://is.gd/g1MIT .  When we switch to
# Eucalyptus, we can dump this.

from_scratch_root = """
# From 'help set':
# -x  Print commands and their arguments as they are executed.
# -e  Exit immediately if a command exits with a non-zero status.
set -xe

# They end up as just one stream; this avoids ordering problems.
exec 2>&1

sed -ie 's/main universe/main universe multiverse/' /etc/apt/sources.list

. /etc/lsb-release

mount -o remount,data=writeback,commit=3600,async,relatime /

cat >> /etc/apt/sources.list << EOF
deb http://ppa.launchpad.net/launchpad/ubuntu $DISTRIB_CODENAME main
deb http://ppa.launchpad.net/bzr/ubuntu $DISTRIB_CODENAME main
EOF

export DEBIAN_FRONTEND=noninteractive

# PPA keys
apt-key adv --recv-keys --keyserver pool.sks-keyservers.net 2af499cb24ac5f65461405572d1ffb6c0a5174af # launchpad
apt-key adv --recv-keys --keyserver pool.sks-keyservers.net ece2800bacf028b31ee3657cd702bf6b8c6c1efd # bzr

aptitude update

# Do this first so later things don't complain about locales:
LANG=C aptitude -y install language-pack-en

aptitude -y full-upgrade

# This next part is cribbed from rocketfuel-setup
dev_host() {
  sed -i \"s/^127.0.0.88.*$/&\ ${hostname}/\" /etc/hosts
}

echo 'Adding development hosts on local machine'
echo '
# Launchpad virtual domains. This should be on one line.
127.0.0.88      launchpad.dev
' >> /etc/hosts

declare -a hostnames
hostnames=$(cat <<EOF
    answers.launchpad.dev
    api.launchpad.dev
    bazaar-internal.launchpad.dev
    beta.launchpad.dev
    blueprints.launchpad.dev
    bugs.launchpad.dev
    code.launchpad.dev
    feeds.launchpad.dev
    id.launchpad.dev
    keyserver.launchpad.dev
    lists.launchpad.dev
    openid.launchpad.dev
    ppa.launchpad.dev
    private-ppa.launchpad.dev
    testopenid.dev
    translations.launchpad.dev
    xmlrpc-private.launchpad.dev
    xmlrpc.launchpad.dev
EOF
    )

for hostname in $hostnames; do
  dev_host;
done

echo '
127.0.0.99      bazaar.launchpad.dev
' >> /etc/hosts

apt-get -y install launchpad-developer-dependencies apache2 apache2-mpm-worker

# Create the ec2test user, give them passwordless sudo.
adduser --gecos "" --disabled-password ec2test
echo 'ec2test\tALL=(ALL) NOPASSWD: ALL' >> /etc/sudoers

mkdir /home/ec2test/.ssh
cat > /home/ec2test/.ssh/config << EOF
CheckHostIP no
StrictHostKeyChecking no
EOF

mkdir /var/launchpad
chown -R ec2test:ec2test /var/www /var/launchpad /home/ec2test/
"""


from_scratch_ec2test = """
# From 'help set':
# -x  Print commands and their arguments as they are executed.
# -e  Exit immediately if a command exits with a non-zero status.
set -xe

# They end up as just one stream; this avoids ordering problems.
exec 2>&1

bzr launchpad-login %(launchpad-login)s
bzr init-repo --2a /var/launchpad
bzr branch lp:~launchpad-pqm/launchpad/devel /var/launchpad/test
bzr branch --standalone lp:lp-source-dependencies /var/launchpad/download-cache
mkdir /var/launchpad/sourcecode
/var/launchpad/test/utilities/update-sourcecode /var/launchpad/sourcecode
"""


postmortem_banner = """\
Postmortem Console. EC2 instance is not yet dead.
It will shut down when you exit this prompt (CTRL-D)

Tab-completion is enabled.
EC2Instance is available as `instance`.
Also try these:
  http://%(dns)s/current_test.log
  ssh -A ec2test@%(dns)s
"""


class EC2Instance:
    """A single EC2 instance."""

    @classmethod
    def make(cls, name, instance_type, machine_id, demo_networks=None,
             credentials=None, region=None):
        """Construct an `EC2Instance`.

        :param name: The name to use for the key pair and security group for
            the instance.
        :type name: `EC2SessionName`
        :param instance_type: One of the AVAILABLE_INSTANCE_TYPES.
        :param machine_id: The AMI to use, or None to do the usual regexp
            matching.  If you put 'based-on:' before the AMI id, it is assumed
            that the id specifies a blank image that should be made into one
            suitable for the other ec2 functions (see `from_scratch_root` and
            `from_scratch_ec2test` above).
        :param demo_networks: A list of networks to add to the security group
            to allow access to the instance.
        :param credentials: An `EC2Credentials` object.
        :param region: A string region name eg 'us-east-1'.
        """
        # This import breaks in the test environment.  Do it here so
        # that unit tests (which don't use this factory) can still
        # import EC2Instance.
        from bzrlib.plugins.launchpad.account import get_lp_login

        # XXX JeroenVermeulen 2009-11-27 bug=489073: EC2Credentials
        # imports boto, which isn't necessarily installed in our test
        # environment.  Doing the import here so that unit tests (which
        # don't use this factory) can still import EC2Instance.
        from devscripts.ec2test.credentials import EC2Credentials

        assert isinstance(name, EC2SessionName)

        # We call this here so that it has a chance to complain before the
        # instance is started (which can take some time).
        user_key = get_user_key()

        if credentials is None:
            credentials = EC2Credentials.load_from_file(region_name=region)

        # Make the EC2 connection.
        account = credentials.connect(name)

        # We do this here because it (1) cleans things up and (2) verifies
        # that the account is correctly set up. Both of these are appropriate
        # for initialization.
        #
        # We always recreate the keypairs because there is no way to
        # programmatically retrieve the private key component, unless we
        # generate it.
        account.collect_garbage()

        if machine_id and machine_id.startswith('based-on:'):
            from_scratch = True
            machine_id = machine_id[len('based-on:'):]
        else:
            from_scratch = False

        # get the image
        image = account.acquire_image(machine_id)

        login = get_lp_login()
        if not login:
            raise BzrCommandError(
                'you must have set your launchpad login in bzr.')

        instance = EC2Instance(
            name, image, instance_type, demo_networks, account,
            from_scratch, user_key, login, region)
        instance._credentials = credentials
        return instance

    def __init__(self, name, image, instance_type, demo_networks, account,
                 from_scratch, user_key, launchpad_login, region):
        self._name = name
        self._image = image
        self._account = account
        self._instance_type = instance_type
        self._demo_networks = demo_networks
        self._boto_instance = None
        self._from_scratch = from_scratch
        self._user_key = user_key
        self._launchpad_login = launchpad_login
        self._region = region

    def log(self, msg):
        """Log a message on stdout, flushing afterwards."""
        # XXX: JonathanLange 2009-05-31 bug=383076: Should delete this and use
        # Python logging module instead.
        sys.stdout.write(msg)
        sys.stdout.flush()

    def start(self):
        """Start the instance."""
        if self._boto_instance is not None:
            self.log('Instance %s already started' % self._boto_instance.id)
            return
        start = time.time()
        self.private_key = self._account.acquire_private_key()
        self.security_group = self._account.acquire_security_group(
            demo_networks=self._demo_networks)
        reservation = self._image.run(
            key_name=self._name, security_groups=[self._name],
            instance_type=self._instance_type)
        self._boto_instance = reservation.instances[0]
        self.log('Instance %s starting..' % self._boto_instance.id)
        while self._boto_instance.state == 'pending':
            self.log('.')
            time.sleep(5)
            self._boto_instance.update()
        if self._boto_instance.state == 'running':
            self.log(' started on %s\n' % self.hostname)
            elapsed = time.time() - start
            self.log('Started in %d minutes %d seconds\n' %
                     (elapsed // 60, elapsed % 60))
            self._output = self._boto_instance.get_console_output()
            self.log(self._output.output)
            self._ec2test_user_has_keys = False
        else:
            raise BzrCommandError(
                "failed to start: %s: %r\n" % (
                    self._boto_instance.state,
                    self._boto_instance.state_reason,
                    ))

    def shutdown(self):
        """Shut down the instance."""
        if self._boto_instance is None:
            self.log('no instance created\n')
            return
        self._boto_instance.update()
        if self._boto_instance.state not in ('shutting-down', 'terminated'):
            self.log("terminating %s..." % self._boto_instance)
            self._boto_instance.terminate()
            self._boto_instance.update()
            self.log(" done\n")
        self.log('instance %s\n' % (self._boto_instance.state,))

    @property
    def hostname(self):
        if self._boto_instance is None:
            return None
        return self._boto_instance.public_dns_name

    def _connect(self, username):
        """Connect to the instance as `user`. """
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(AcceptAllPolicy())
        self.log('ssh connect to %s: ' % self.hostname)
        connect_args = {
            'username': username,
            'pkey': self.private_key,
            'allow_agent': False,
            'look_for_keys': False,
            }
        for count in range(20):
            caught_errors = (
                socket.error,
                paramiko.AuthenticationException,
                EOFError,
                )
            try:
                ssh.connect(self.hostname, **connect_args)
            except caught_errors as e:
                self.log('.')
                not_connected = [
                    errno.ECONNREFUSED,
                    errno.ETIMEDOUT,
                    errno.EHOSTUNREACH,
                    ]
                if getattr(e, 'errno', None) not in not_connected:
                    self.log('ssh _connect: %r\n' % (e,))
                if count < 9:
                    time.sleep(5)
                else:
                    raise
            else:
                break
        self.log(' ok!\n')
        return EC2InstanceConnection(self, username, ssh)

    def _upload_local_key(self, conn, remote_filename):
        """Upload a key from the local user's agent to `remote_filename`.

        The key will be uploaded in a format suitable for
        ~/.ssh/authorized_keys.
        """
        authorized_keys_file = conn.sftp.open(remote_filename, 'w')
        authorized_keys_file.write(
            "%s %s\n" % (
                self._user_key.get_name(), self._user_key.get_base64()))
        authorized_keys_file.close()

    def _ensure_ec2test_user_has_keys(self, connection=None):
        """Make sure that we can connect over ssh as the 'ec2test' user.

        We add both the key that was used to start the instance (so
        _connect('ec2test') works and a key from the locally running ssh agent
        (so EC2InstanceConnection.run_with_ssh_agent works).
        """
        if not self._ec2test_user_has_keys:
            if connection is None:
                connection = self._connect('ubuntu')
                our_connection = True
            else:
                our_connection = False
            self._upload_local_key(connection, 'local_key')
            connection.perform(
                'cat /home/ubuntu/.ssh/authorized_keys local_key '
                '| sudo tee /home/ec2test/.ssh/authorized_keys > /dev/null'
                '&& rm local_key')
            connection.perform('sudo chown -R ec2test:ec2test /home/ec2test/')
            connection.perform('sudo chmod 644 /home/ec2test/.ssh/*')
            if our_connection:
                connection.close()
            self.log(
                'You can now use ssh -A ec2test@%s to '
                'log in the instance.\n' % self.hostname)
            self._ec2test_user_has_keys = True

    def connect(self):
        """Connect to the instance as a user with passwordless sudo.

        This may involve first connecting as root and adding SSH keys to the
        user's account, and in the case of a from scratch image, it will do a
        lot of set up.
        """
        if self._from_scratch:
            ubuntu_connection = self._connect('ubuntu')
            self._upload_local_key(ubuntu_connection, 'local_key')
            ubuntu_connection.perform(
                'cat local_key >> ~/.ssh/authorized_keys && rm local_key')
            ubuntu_connection.run_script(from_scratch_root, sudo=True)
            self._ensure_ec2test_user_has_keys(ubuntu_connection)
            ubuntu_connection.close()
            conn = self._connect('ec2test')
            conn.run_script(
                from_scratch_ec2test
                % {'launchpad-login': self._launchpad_login})
            self._from_scratch = False
            self.log('done running from_scratch setup\n')
            return conn
        self._ensure_ec2test_user_has_keys()
        return self._connect('ec2test')

    def _report_traceback(self):
        """Print traceback."""
        traceback.print_exc()

    def set_up_and_run(self, postmortem, shutdown, func, *args, **kw):
        """Start, run `func` and then maybe shut down.

        :param config: A dictionary specifying details of how the instance
            should be run:
        :param postmortem: If true, any exceptions will be caught and an
            interactive session run to allow debugging the problem.
        :param shutdown: If true, shut down the instance after `func` and
            postmortem (if any) are completed.
        :param func: A callable that will be called when the instance is
            running and a user account has been set up on it.
        :param args: Passed to `func`.
        :param kw: Passed to `func`.
        """
        # We ignore the value of the 'shutdown' argument and always shut down
        # unless `func` returns normally.
        really_shutdown = True
        retval = None
        try:
            self.start()
            try:
                retval = func(*args, **kw)
            except Exception:
                # When running in postmortem mode, it is really helpful to see
                # if there are any exceptions before it waits in the console
                # (in the finally block), and you can't figure out why it's
                # broken.
                self._report_traceback()
            else:
                really_shutdown = shutdown
        finally:
            try:
                if postmortem:
                    console = code.InteractiveConsole(locals())
                    console.interact(
                        postmortem_banner % {'dns': self.hostname})
                    print 'Postmortem console closed.'
            finally:
                if really_shutdown:
                    self.shutdown()
        return retval

    def _copy_single_file(self, sftp, local_path, remote_dir):
        """Copy `local_path` to `remote_dir` on this instance.

        The name in the remote directory will be that of the local file.

        :param sftp: A paramiko SFTP object.
        :param local_path: The local path.
        :param remote_dir: The directory on the instance to copy into.
        """
        name = os.path.basename(local_path)
        remote_path = os.path.join(remote_dir, name)
        remote_file = sftp.open(remote_path, 'w')
        remote_file.write(open(local_path).read())
        remote_file.close()
        return remote_path

    def copy_key_and_certificate_to_image(self, sftp):
        """Copy the AWS private key and certificate to the image.

        :param sftp: A paramiko SFTP object.
        """
        remote_ec2_dir = '/mnt/ec2'
        remote_pk = self._copy_single_file(
            sftp, self.local_pk, remote_ec2_dir)
        remote_cert = self._copy_single_file(
            sftp, self.local_cert, remote_ec2_dir)
        return (remote_pk, remote_cert)

    def _check_single_glob_match(self, local_dir, pattern, file_kind):
        """Check that `pattern` matches one file in `local_dir` and return it.

        :param local_dir: The local directory to look in.
        :param pattern: The glob patten to match.
        :param file_kind: The sort of file we're looking for, to be used in
            error messages.
        """
        pattern = os.path.join(local_dir, pattern)
        matches = glob.glob(pattern)
        if len(matches) != 1:
            raise BzrCommandError(
                '%r must match a single %s file' % (pattern, file_kind))
        return matches[0]

    def check_bundling_prerequisites(self, name):
        """Check, as best we can, that all the files we need to bundle exist.
        """
        local_ec2_dir = os.path.expanduser('~/.ec2')
        if not os.path.exists(local_ec2_dir):
            raise BzrCommandError(
                "~/.ec2 must exist and contain aws_user, aws_id, a private "
                "key file and a certificate.")
        aws_user_file = os.path.expanduser('~/.ec2/aws_user')
        if not os.path.exists(aws_user_file):
            raise BzrCommandError(
                "~/.ec2/aws_user must exist and contain your numeric AWS id.")
        self.aws_user = open(aws_user_file).read().strip()
        self.local_cert = self._check_single_glob_match(
            local_ec2_dir, 'cert-*.pem', 'certificate')
        self.local_pk = self._check_single_glob_match(
            local_ec2_dir, 'pk-*.pem', 'private key')
        # The bucket `name` needs to exist and be accessible. We create it
        # here to reserve the name. If the bucket already exists and conforms
        # to the above requirements, this is a no-op.
        #
        # The API for region creation is a little quirky: you apparently can't
        # explicitly ask for 'us-east-1' you must just say '', etc.
        location = self._credentials.region_name
        if location.startswith('us-east'):
            location = ''
        elif location.startswith('eu'):
            location = 'EU'
        self._credentials.connect_s3().create_bucket(
            name, location=location)

    def bundle(self, name, credentials):
        """Bundle, upload and register the instance as a new AMI.

        :param name: The name-to-be of the new AMI, eg 'launchpad-ec2test500'.
        :param credentials: An `EC2Credentials` object.
        """
        connection = self.connect()
        # See http://is.gd/g1MIT .  When we switch to Eucalyptus, we can dump
        # this installation of the ec2-ami-tools.
        connection.perform(
            'sudo env DEBIAN_FRONTEND=noninteractive '
            'apt-get -y  install ec2-ami-tools')
        connection.perform('rm -f .ssh/authorized_keys')
        connection.perform('sudo mkdir /mnt/ec2')
        connection.perform('sudo chown $USER:$USER /mnt/ec2')

        remote_pk, remote_cert = self.copy_key_and_certificate_to_image(
            connection.sftp)

        bundle_dir = os.path.join('/mnt', name)

        connection.perform('sudo mkdir ' + bundle_dir)
        connection.perform(' '.join([
            'sudo ec2-bundle-vol',
            '-d %s' % bundle_dir,
            '--batch',   # Set batch-mode, which doesn't use prompts.
            '-k %s' % remote_pk,
            '-c %s' % remote_cert,
            '-u %s' % self.aws_user,
            ]))

        # Assume that the manifest is 'image.manifest.xml', since "image" is
        # the default prefix.
        manifest = os.path.join(bundle_dir, 'image.manifest.xml')

        # Best check that the manifest actually exists though.
        test = 'test -f %s' % manifest
        connection.perform(test)

        connection.perform(' '.join([
            'sudo ec2-upload-bundle',
            '-b %s' % name,
            '-m %s' % manifest,
            '-a %s' % credentials.identifier,
            '-s %s' % credentials.secret,
            ]))

        connection.close()

        # This is invoked locally.
        mfilename = os.path.basename(manifest)
        manifest_path = os.path.join(name, mfilename)

        now = datetime.strftime(datetime.utcnow(), "%Y-%m-%d %H:%M:%S UTC")
        description = "launchpad ec2test created %s by %r on %s" % (
            now,
            os.environ.get('EMAIL', '<unknown>'),
            socket.gethostname())

        self.log('registering image: ')
        image_id = credentials.connect('bundle').conn.register_image(
            name=name,
            description=description,
            image_location=manifest_path,
            )
        self.log('ok\n')
        self.log('** new instance: %r\n' % (image_id,))


class EC2InstanceConnection:
    """An ssh connection to an `EC2Instance`."""

    def __init__(self, instance, username, ssh):
        self._instance = instance
        self._username = username
        self._ssh = ssh
        self._sftp = None

    @property
    def sftp(self):
        if self._sftp is None:
            self._sftp = self._ssh.open_sftp()
        if self._sftp is None:
            raise AssertionError("failed to open sftp connection")
        return self._sftp

    def perform(self, cmd, ignore_failure=False, out=None, err=None):
        """Perform 'cmd' on server.

        :param ignore_failure: If False, raise an error on non-zero exit
            statuses.
        :param out: A stream to write the output of the remote command to.
        :param err: A stream to write the error of the remote command to.
        """
        if out is None:
            out = sys.stdout
        if err is None:
            err = sys.stderr
        self._instance.log(
            '%s@%s$ %s\n'
            % (self._username, self._instance._boto_instance.id, cmd))
        session = self._ssh.get_transport().open_session()
        session.exec_command(cmd)
        session.shutdown_write()
        while 1:
            try:
                select.select([session], [], [], 0.5)
            except (IOError, select.error), e:
                if e.errno == errno.EINTR:
                    continue
            if session.recv_ready():
                data = session.recv(4096)
                if data:
                    out.write(data)
                    out.flush()
            if session.recv_stderr_ready():
                data = session.recv_stderr(4096)
                if data:
                    err.write(data)
                    err.flush()
            if session.exit_status_ready():
                break
        session.close()
        # XXX: JonathanLange 2009-05-31: If the command is killed by a signal
        # on the remote server, the SSH protocol does not send an exit_status,
        # it instead sends a different message with the number of the signal
        # that killed the process. AIUI, this code will fail confusingly if
        # that happens.
        res = session.recv_exit_status()
        if res and not ignore_failure:
            raise RuntimeError('Command failed: %s' % (cmd,))
        return res

    def run_with_ssh_agent(self, cmd, ignore_failure=False):
        """Run 'cmd' in a subprocess.

        Use this to run commands that require local SSH credentials. For
        example, getting private branches from Launchpad.
        """
        self._instance.log(
            '%s@%s$ %s\n'
            % (self._username, self._instance._boto_instance.id, cmd))
        call = ['ssh', '-A', self._username + '@' + self._instance.hostname,
               '-o', 'CheckHostIP no',
               '-o', 'StrictHostKeyChecking no',
               '-o', 'UserKnownHostsFile ~/.ec2/known_hosts',
               cmd]
        res = subprocess.call(call)
        if res and not ignore_failure:
            raise RuntimeError('Command failed: %s' % (cmd,))
        return res

    def run_script(self, script_text, sudo=False):
        """Upload `script_text` to the instance and run it with bash."""
        script = self.sftp.open('script.sh', 'w')
        script.write(script_text)
        script.close()
        cmd = '/bin/bash script.sh'
        if sudo:
            cmd = 'sudo ' + cmd
        self.run_with_ssh_agent(cmd)
        # At least for mwhudson, the paramiko connection often drops while the
        # script is running.  Reconnect just in case.
        self.reconnect()
        self.perform('rm script.sh')

    def reconnect(self):
        """Close the connection and reopen it."""
        self.close()
        self._ssh = self._instance._connect(self._username)._ssh

    def close(self):
        if self._sftp is not None:
            self._sftp.close()
            self._sftp = None
        self._ssh.close()
        self._ssh = None
