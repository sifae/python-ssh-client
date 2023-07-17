import paramiko
import os
import time
import stat

class SFTP(paramiko.SFTPClient):
    def put_dir(self, source : str, target : str) -> None:
        ''' Uploads the contents of the source directory to the target path. The
            target directory needs to exists. All subdirectories in source are 
            created under target.
        '''
        for item in os.listdir(source):
            if os.path.isfile(os.path.join(source, item)):
                self.put(os.path.join(source, item), '%s/%s' % (target, item))
            else:
                self.mkdir('%s/%s' % (target, item), ignore_existing=True)
                self.put_dir(os.path.join(source, item), '%s/%s' % (target, item))

    def mkdir(self, path : str, mode : int = 511, ignore_existing : bool = False) -> None:
        ''' Augments mkdir by adding an option to not fail if the folder exists  '''
        try:
            super(SFTP, self).mkdir(path, mode)
        except IOError:
            if ignore_existing:
                pass
            else:
                raise
    
    def rmdir(self, path : str) -> None:
        ''' Removes directory recursively '''
        for file, fileattr in zip(self.listdir(path), self.listdir_attr(path)):
            subpath = os.path.join(path, file)
            if stat.S_ISDIR(fileattr.st_mode):
                self.rmdir(subpath)
            else:
                self.remove(subpath)
        super(SFTP, self).rmdir(path)

    def get(self, remotepath : str, localpath : str) -> None:
        ''' Downloads directory recursively '''
        for file, fileattr in zip(self.listdir(remotepath), self.listdir_attr(remotepath)):
            remote_subpath = os.path.join(remotepath, file)
            local_subpath = os.path.join(localpath, file)
            if stat.S_ISDIR(fileattr.st_mode):
                os.mkdir(local_subpath)
                self.get(remote_subpath, local_subpath)
            else:
                super(SFTP, self).get(remote_subpath, local_subpath)


class SSH:
    _ssh_client : paramiko.SSHClient = None
    _ssh_output : str = ""
    _ssh_last_output : str = ""
    
    _sftp_client : SFTP = None

    _transport : paramiko.Transport = None
    
    _max_recv_size : int = 1024

    def __init__(self, host : str, port : int, username : str, password : str):
        print("Connecting to host '%s' \n" % host)
        self._ssh_client = paramiko.client.SSHClient()
        self._ssh_client.set_missing_host_key_policy(paramiko.client.AutoAddPolicy())
        self._ssh_client.connect(host, port, username, password, look_for_keys=False)

        self._transport = self._ssh_client.get_transport()
        
        self._sftp_client = SFTP.from_transport(self._transport)

    def __del__(self):
        connections = [
            self._sftp_client,
            self._transport,
            self._ssh_client,
        ] 
        for connection in connections:
            if connection:
                connection.close()

    def exec(self, command : str):
        channel = self._transport.open_session()
        channel.set_combine_stderr(True)
        channel.exec_command(command)
        self._read_ssh_output(channel)
        print(self._ssh_last_output)
        channel.close()

    def get_ssh_output(self) -> str:
        return self._ssh_output
    
    def upload(self, src : str, dst : str):
        self._sftp_client.mkdir(dst, ignore_existing=True)
        if os.path.isdir(src):
            self._sftp_client.put_dir(src, dst)
        elif os.path.isfile(src):
            self._sftp_client.put(src, dst)
        else:
            raise Exception("%s does not exist" % src)

    def download(self, src : str, dst : str):
        self._sftp_client.get(src, dst)

    def delete(self, path : str):
        try:
            self._sftp_client.remove(path)
        except IOError:
            self._sftp_client.rmdir(path)
    
    def _read_ssh_output(self, channel : paramiko.Channel):
        while True:
            # Write data when available
            if channel.exit_status_ready():
                data = channel.recv(self._max_recv_size)
                while channel.recv_ready():
                    data += channel.recv(self._max_recv_size)
                data = data.decode("utf-8")
                self._ssh_output += data
                self._ssh_last_output = data
                break
            else:
                time.sleep(0.1)
