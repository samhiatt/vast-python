import getpass
import os
import requests
import json
from requests.exceptions import HTTPError
from urllib.parse import quote_plus
from collections import namedtuple
from paramiko.client import SSHClient, AutoAddPolicy
from paramiko.ssh_exception import NoValidConnectionsError
from vastai.exceptions import APIError, Unauthorized, PrivateSshKeyNotFound

default_api_key_file = os.path.join(os.environ['HOME'],'.vast_api_key')
api_base_url = "https://vast.ai/api/v0"

class VastClient:
    """
    Vast.ai Account  
    Handles account configuration and authentication and provides get_instances method.
    By default, looks for VAST_API_KEY env variable or ~/.vast_api_key for existing credentials. 
    """
    def __init__(self, api_key_file=default_api_key_file, ssh_key_dir=None):
        """
        Initialize VastClient object.  
        Args:
            api_key_file (str, optional): Path to file in which to save api_key. 
                (default "~/.vast_api_key") Will not save to disk if this is set to None or False.
            ssh_key_dir (str, optional): Path to directory containing ssh key for connecting to vast.ai 
                instances. (default: ~/.ssh/)
        """
        self.api_key_file = api_key_file 
        print("api_key_file: ",api_key_file)
        #self.api_key_file = os.path.expanduser(api_key_file) if api_key_file \
        #                   else os.path.join(os.environ['HOME'],'.vast_api_key')
        self.ssh_key_dir = os.path.expanduser(ssh_key_dir) if ssh_key_dir \
                           else os.path.join(os.environ['HOME'],'.ssh')
        self.ssh_key = None
        self.api_key = None
        self.instance_ids = []
        if 'VAST_API_KEY' in os.environ: 
            print("Initializing vast.ai client with api_key from VAST_API_KEY env var.")
            self.api_key = os.environ['VAST_API_KEY']
        elif self.api_key_file and os.path.exists(self.api_key_file):
            with open(self.api_key_file) as f:
                print("Initializing vast.ai client with api_key from %s."%self.api_key_file)
                self.api_key = f.read()
        else:
            print("No api_key set. Call `login` to retrieve%s."%\
                 ((" and save in "+self.api_key_file) if self.api_key_file else ""))
            

    def login(self, username=None, password=None):
        """
        Get api_key using username and password.
        Args:
            username (str, optional): Vast.ai account username. Looks for 
                in VAST_USERNAME env variable if not provided here. 
            password (str, optional): Vast.ai login password. If not provided here
                looks for password in VAST_PASSWORD env variable or uses 
                `getpass` prompt. 
            api_key_file (str): Path to file in which to save api_key. 
                (default "~/.vast_api_key") If `None` api_key will not be stored.
        """
        save_api_key = True 
        if self.api_key: 
            print("Already logged in.")
            save_api_key = False # Flag to skip saving api_key since we already have it.
        else:
            if username is None:
                if 'VAST_USERNAME' in os.environ:
                    username = os.environ['VAST_USERNAME']
                else:
                    username = input("Username or Email: ")
            if password is None:
                if 'VAST_PASSWORD' in os.environ:
                    password = os.environ['VAST_PASSWORD']
                else:
                    try:
                        # weird try/except is because windows gives a typeerror on this line
                        password = getpass.getpass("Password: ")
                    except TypeError:
                        try:
                            password = getpass.getpass("Password: ".encode("utf-8"))
                        except TypeError:
                            password = raw_input("Password: ")
        try:
            url = self._apiurl("/users/current/")
            if self.api_key:
              r = requests.get(url) 
            else:
              r = requests.put(url, json={'username': username, 'password': password} )
            r.raise_for_status()
            resp = r.json()
            # print("Login response:\n",json.dumps(resp))
            for key in resp.keys():
                setattr(self, key, resp[key])
            if self.api_key_file and save_api_key: 
                print("Saving api_key to %s."%self.api_key_file)
                with open(self.api_key_file, 'w') as f:
                    f.write(resp['api_key'])
            return self
            
        except HTTPError as err:
            if self.api_key:
                raise Unauthorized("Error logging in with api key.")
            else:
                raise Unauthorized("Error logging in as %s."%username)
            
    def _get_ssh_key_file(self):
        """ Returns the path to a public ssh key used to log into remote 
            vast.ai machines. 
        Args:
            key_dir (str, optional): Path to directory with ssh keys. 
                (default: '~/.ssh/')
        Raises:
            PrivateSshKeyNotFound: If private ssh key matching `self.ssh_key` 
                is not found in `key_dir`.
            SshKeyNotSet: If `self.ssh_key` is not set.
        """
        if self.ssh_key is None:
            raise(Unauthorized())
        for file in os.listdir(key_dir):
            pub_key_file = os.path.join(sekf.ssh_key_dir, file+'.pub')
            # print (self.ssh_key)
            if os.path.exists(pub_key_file):
                with open(pub_key_file) as f:
                    # k = f.read()
                    # print(k)
                    if f.read().strip()==self.ssh_key.strip(): 
                        return pub_key_file[:-4]
        raise PrivateSshKeyNotFound(key_dir, self.ssh_key)
        
    def get_instance(self, id):
        self.get_instances()
        idx = self.instance_ids.index(id)
        return self.instances[idx] if idx >= 0 else None
        
    def get_instances(self):
        """ Retrievs a list of user's configured instances.
        Returns: 
            :`list`: of :obj:`Instance`: A list of configured Instances. 
        Raises: 
            ApiKeyNotSet: if user.api_key is not set.
        """
        if self.api_key is None: raise ApiKeyNotSet()
        
        req_url = self._apiurl("/instances", owner="me");
        r = requests.get(req_url);
        r.raise_for_status()
        # print(json.dumps(r.json()))
        instances = r.json()["instances"]
        self.instance_ids = [instance['id'] for instance in instances]
        self.instances = [Instance(self, **instance) for instance in instances]
        return self.instances
    
    def _apiurl(self, subpath, **kwargs):
        query_args = {}
        if self.api_key is not None:
            query_args["api_key"] = self.api_key
        if query_args:
            return api_base_url + subpath + "?" + "&".join("{x}={y}".format(
                    x=x, y=quote_plus(y if isinstance(y, str) else json.dumps(y))) 
                for x, y in query_args.items())
        else:
            return api_base_url + subpath

_InstanceField = namedtuple('InstanceField',"name format conversion")
_displayable_fields = dict(
    id =                   _InstanceField("ID",       "{}",       None),
    actual_status =        _InstanceField("Status",   "{}",       None),
    # cuda_max_good =        _InstanceField("CUDA",     "{:0.1f}",  None),
    gpu_name =             _InstanceField("Model",    "{}",       None),
    # pcie_bw =              _InstanceField("PCIE BW",  "{:0.1f}",  None),
    num_gpus =             _InstanceField("GPUs",      "{}X",     None),
    cpu_cores_effective =  _InstanceField("vCPUs",    "{:.0f}X",  None),
    cpu_ram =              _InstanceField("RAM",      "{:0.1f}",  lambda x: x/1000),
    disk_space =           _InstanceField("Storage",  "{:.0f}GB",     None),
    dph_total =            _InstanceField("Cost",     "${:0.4f}/hr",  None),
    # dlperf =               _InstanceField("DLPerf",   "{:0.1f}",   None),
    # dlperf_per_dphtotal =  _InstanceField("DLP/$",    "{:0.1f}",   None),
    inet_up =              _InstanceField("Net up",   "{:0.1f}",   None),
    inet_down =            _InstanceField("Net down", "{:0.1f}",   None),
    reliability2 =         _InstanceField("Reliability","{:0.1f}", lambda x: x * 100),
    duration =             _InstanceField("Days Remaining", "{:0.1f}",   lambda x: x/(24.0*60.0*60.0)),
)

class Instance:
    def __init__(self, user, **kwargs):
        self.fields=[]
        self.user = user
        for key in kwargs.keys():
            setattr(self, key, kwargs[key])
            self.fields.append(key)
        self.status = self.actual_status if hasattr(self, 'actual_status') else None
    def __repr__(self):
        res = []
        for key, field in _displayable_fields.items():
            val = getattr(self,key) or ''
            if field.conversion: val = field.conversion(val) if val else None
            res.append(field.name+": "+(field.format.format(val) if val else '-'))
        return ', '.join(res)
    def __dict__(self):
        return {k:getattr(self,k) for k in self.fields}
        
    def start(self):
        """ Start a configured instance.
        Raises: APIError
        """
        url = self.user._apiurl("/instances/%s/"%self.id)
        r = requests.put(url, json={ "state": "running" })
        r.raise_for_status()
        if (r.status_code == 200):
            rj = r.json()
            # print(json.dumps(rj))
            if (rj["success"]):
                print("Starting instance %i."%self.id )
            else:
                raise APIError(self.id, rj["msg"])
        else:
            print("Start instance request failed with error: %s"%r.status_code)
            raise APIError(self.id, r.text)
            
    def stop(self):
        """ Stop a configured instance.
        Raises: APIError
        """
        url = self.user._apiurl("/instances/%s/"%self.id)
        r = requests.put(url, json={"state": "stopped"})
        r.raise_for_status()
        if (r.status_code == 200):
            rj = r.json()
            if (rj["success"]):
                print("Stopping instance %i."%self.id )
            else:
                raise APIError(self.id, 
                    "Error stopping instance.\n%s"%rj["msg"])
        else:
            raise APIError(self.id, 
                "Stop instance request failed with error: %s\n%s"%(r.status_code,r.text))
            
    def destroy(self):
        url = self.user._apiurl("/instances/%s/"%self.id)
        r = requests.delete(url, json={})
        r.raise_for_status()
        if (r.status_code == 200):
            rj = r.json();
            if (rj["success"]):
                print("Destroying instance %s."%self.id )
            else:
                raise APIError(self.id, 
                    "Error destroying instance.\n%s"%rj["msg"])
        else:
            raise APIError(self.id, 
                "Destroy instance request failed with error: %s\n%s"%(r.status_code,r.text))
            
    def run_command(self, command_str):
        """
            Executes `command_str` on this vast.ai instance.
        """
        ssh_client = SSHClient()
        ssh_client.set_missing_host_key_policy(AutoAddPolicy)
        print("Connecting to %s:%i "%(self.ssh_host,self.ssh_port))
        try:
            ssh_client.connect(self.ssh_host, port=int(self.ssh_port), 
                       username='root', key_filename=self.user.get_ssh_key_file())
            print("Running command '%s'"%command_str)
            stdin, stdout, stderr = ssh_client.exec_command(command_str)
            print(stdout.read().decode('utf-8'))
            print(stderr.read().decode('utf-8'))
    
        # except NoValidConnectionsError as err:
        #     raise APIError(self.id, err.errors)
        # except Exception as err:
        #     raise APIError(self.id, str(err))
        finally:
            ssh_client.close()
            
      
