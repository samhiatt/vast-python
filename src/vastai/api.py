import logging
import getpass
import os
import requests
import json
from requests.exceptions import HTTPError
from urllib.parse import quote_plus
from collections import namedtuple
from paramiko.client import SSHClient, AutoAddPolicy
from paramiko.ssh_exception import NoValidConnectionsError
from vastai.exceptions import InstanceError, Unauthorized, PrivateSshKeyNotFound
from vastai.vast import display_table, displayable_fields
import sys, io

default_api_key_file = os.path.join('~','.vast_api_key')
default_ssh_key_dir = os.path.join('~','.ssh')
api_base_url = "https://vast.ai/api/v0"

class VastClient:
    """
    # Vast.ai API Client  
    Handles account configuration and authentication and provides get_instances method.
    By default, looks for `VAST_API_KEY` env variable or `~/.vast_api_key` for existing credentials.
    If `api_key_file` is explicitly set to None then the API key won't be written to disk. 
    """
    def __init__(self, api_key_file=default_api_key_file, ssh_key_dir=default_ssh_key_dir):
        """
        Initialize VastClient object.  
        Args:
            api_key_file (str, optional): Path to file in which to save api_key. 
                (default "~/.vast_api_key") Will not save to disk if this is set to None or False.
            ssh_key_dir (str, optional): Path to directory containing ssh key for connecting to vast.ai 
                instances. (default: ~/.ssh/)
        """
        self.api_key_file = os.path.expanduser(api_key_file) if api_key_file else None
        print("api_key_file: ",api_key_file)
        self.ssh_key_dir = os.path.expanduser(ssh_key_dir) 
        self.ssh_key = None
        self.api_key = None
        self.instance_ids = []
        self.instances = []
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
            

    def authenticate(self, username=None, password=None):
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
        Returns:
            VastClient: Self
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
        
    def get_instances(self):
        """ Retrieves a list of user's configured instances.
        Returns:
            `InstanceList`: A list of configured `Instance`s.
        Raises:
            `ApiKeyNotSet`: If `self.api_key` is not set. 
        """
        if self.api_key is None: raise ApiKeyNotSet()
        
        req_url = self._apiurl("/instances", owner="me");
        r = requests.get(req_url);
        r.raise_for_status()
        # print(json.dumps(r.json()))
        instances = r.json()["instances"]
        self.instance_ids = [instance['id'] for instance in instances]
        self.instances = InstanceList([Instance(self, **instance) for instance in instances])
        return self.instances
    
    def get_instance(self, id):
        """ Get a configured `Instance` by id.
        Args:
            id (str): vast.ai instance id.
        Returns:
            `Instance`
        """
        self.get_instances()
        idx = self.instance_ids.index(id)
        return self.instances[idx] if idx >= 0 else None
        
    def _apiurl(self, subpath, **kwargs):
        query_args = {}
        for k in kwargs:
            query_args[k] = kwargs[k]
        if self.api_key is not None:
            query_args["api_key"] = self.api_key
        if query_args:
            return api_base_url + subpath + "?" + "&".join("{x}={y}".format(
                    x=x, y=quote_plus(y if isinstance(y, str) else json.dumps(y))) 
                for x, y in query_args.items())
        else:
            return api_base_url + subpath


def _grab_display_table_out(instances):
    output = io.StringIO()
    sys.stdout = output
    display_table(instances, displayable_fields)
    sys.stdout = sys.__stdout__
    result = output.getvalue()
    return result    

class InstanceList(list):
    """ A list of `Instance`s, returned by `VastClient.get_instances()`
    """
    def __dict__(self):
        return {i.id:i.__dict__() for i in self}
    def __json__(self):
        return json.dumps([i.__dict__() for i in self])
    def __repr__(self):
        return _grab_display_table_out(self)

class Instance:
    def __init__(self, client, **kwargs):
        """ Vast.ai Instance, instantiated by `VastClient.get_instances()`.  
            TODO: document Instance params
        Params:
            client (VastClient): 
            **kwargs
        """
        self.fields=[]
        self.client = client
        for key in kwargs.keys():
            setattr(self, key, kwargs[key])
            self.fields.append(key)
        self.status = self.actual_status if hasattr(self, 'actual_status') else None

    def __repr__(self):
        """ Uses `vast.display_table` for display.
        """
        return _grab_display_table_out([self])

    def __dict__(self):
        """ Gets dict of serializable fields.
        """
        return {k:getattr(self,k) for k in self.fields}

    def __json__(self):
        """ Gets JSON serializable string
        """
        return json.dumps(self.__dict__())

    def get(self, attr, default=None):
        """ Gets a specified attribute from this Instance. 
            Used by vastai.vast.display_table.
        Args:
            attr (str): Instance attribute
            default: Default value, if attribute not found. (default: None)
        """
        return getattr(self, attr) if hasattr(self, attr) else default

    def _request(self, method, json_data):
        """ Makes http request to `<api_base_url>/instances/<instance.id>/` 
        Params:
            method (str): HTTP request method.
            json_data (json): JSON data to send in request body.
        Raises:
            InstanceError: if request doesn't return data['success']
        """
        assert type(method) is str
        assert method.lower() in ['get', 'put', 'post', 'update', 'delete']
        url = self.client._apiurl("/instances/%s/"%self.id)
        resp = requests.request(method, url, json=json_data)
        resp.raise_for_status()
        if resp.status_code == 200:
            resp_data = resp.json()
            if resp_data['success']:
                logging.info(json.dumps(resp_data))
                return resp_data
            else:
                logging.debug(json.dumps(resp_data))
                raise InstanceError(resp_data['msg'], self.id)
        else:
            logging.debug(resp)
            raise InstanceError(resp, self.id)
        
    def start(self):
        """ Starts this configured instance.
        Args:
            None
        Raises: 
            InstanceError: if request doesn't return data['success']
        """
        self._request('put',{ "state": "running" })
        print("Starting instance %i."%self.id )

    def stop(self):
        """ Stops this configured instance. You can restart the instance later. 
        Args:
            None
        Raises: 
            InstanceError: if request doesn't return data['success']
        """
        self._request('put', {"state": "stopped"})
        print("Stopping instance %i."%self.id )

    def destroy(self):
        """ Destroys this configured instance. All data on the remote instance will be lost.
        Args:
            None
        Raises: 
            InstanceError: if request doesn't return data['success']
        """
        self._request('delete',{})
        print("Destroying instance %s"%self.id)
            
    def run_command(self, command_str):
        """
            Uses paramiko ssh client to execute `command_str` on this remote Instance.
        Args:
            command_str (str): The remote shell command to execute.
        """
        ssh_client = SSHClient()
        ssh_client.set_missing_host_key_policy(AutoAddPolicy)
        print("Connecting to %s:%i "%(self.ssh_host,self.ssh_port))
        try:
            ssh_client.connect(self.ssh_host, port=int(self.ssh_port), username='root', 
                               key_filename=self.client.get_ssh_key_file())
            print("Running command '%s'"%command_str)
            stdin, stdout, stderr = ssh_client.exec_command(command_str)
            print(stdout.read().decode('utf-8'))
            print(stderr.read().decode('utf-8'))
    
        # except NoValidConnectionsError as err:
        #     raise InstanceError(self.id, err.errors)
        finally:
            ssh_client.close()
            
      
