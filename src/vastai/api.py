#import logging
import os
import requests
import json
from requests.exceptions import HTTPError
from urllib.parse import quote_plus
from collections import namedtuple
from paramiko.client import SSHClient, AutoAddPolicy
from paramiko.ssh_exception import NoValidConnectionsError
from paramiko import RSAKey
import sys
from vastai.exceptions import InstanceError, Unauthorized, PrivateSshKeyNotFound, UnhandledSetupError
from vastai.vast import displayable_fields, instance_fields, parse_query
import pandas as pd
import time
from plumbum.machines.paramiko_machine import ParamikoMachine
from plumbum.machines.remote import ClosedRemote, ClosedRemoteMachine
from plumbum.machines import SshMachine
from paramiko.client import AutoAddPolicy

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
            VastClient: self
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
            `vastai.exceptions.PrivateSshKeyNotFound`: If private ssh key matching `self.ssh_key` 
                is not found in `key_dir`.
            `vastai.exceptions.SshKeyNotSet`: If `self.ssh_key` is not set.
        """
        if self.ssh_key is None:
            raise(Unauthorized())
        for file in os.listdir(self.ssh_key_dir):
            pub_key_file = os.path.join(self.ssh_key_dir, file+'.pub')
            # print (self.ssh_key)
            if os.path.exists(pub_key_file):
                with open(pub_key_file) as f:
                    if f.read().strip()==self.ssh_key.strip(): 
                        return pub_key_file[:-4]
        raise PrivateSshKeyNotFound(key_dir, self.ssh_key)

    def create_ssh_key(self, name='vastai'):
        """ Generate a new ssh RSA token that can be used for connecting to remote instances.
        Args: 
            name (str): Name for the RSA key pair. Public key will be named 
                        '{{self.ssh_key_dir}}/{{name}}.pub'. (default: 'vastai')
        Returns:
            str: Path to new public ssh key file.
        """
        if not os.path.isdir(self.ssh_key_dir):
            print("Creating new directory for ssh key file: %s"%self.ssh_key_dir)
            os.path.mkdir(self.ssh_key_dir)
        key = RSAKey.generate(4096)
        public_key_file = os.path.join(self.ssh_key_dir, "%s.pub"%name)
        private_key_file = os.path.join(self.ssh_key_dir, name)
        print("Saving RSA key pair: %s\n    Private key: %s"%(public_key_file, private_key_file))
        with open(public_key_file,'w') as f:
            f.write(key.get_base64())
        key.write_private_key_file(private_key_file)
        return public_key_file

        
    def get_instances(self, retries=2, retry_delay_s=5):
        """ Retrieves a list of user's configured instances.
        Raises:
            `vastai.exceptions.ApiKeyNotSet`: If `self.api_key` is not set. 
        Returns:
            InstanceList: A list of configured `Instance`s.
        """
        if self.api_key is None: raise ApiKeyNotSet()
        
        req_url = self._apiurl("/instances", owner="me")
        try:
            r = requests.get(req_url)
            r.raise_for_status()
            resp = r.json()
        except HTTPError:
            if retries>0:
                time.sleep(retry_delay_s)
                return self.get_instances(retries=retries-1, 
                                          retry_delay_s=retry_delay_s)
            raise
        # Merge with existing Instances
        for instance_latest in resp["instances"]:
            if instance_latest['id'] in self.instance_ids: 
                # merge with existing
                instance_idx = self.instance_ids.index(instance_latest['id'])
                instance = self.instances[instance_idx]
                for field in self.instances[instance_idx].fields:
                    setattr(instance, field, instance_latest[field])
                instance.status=instance_latest['actual_status']
            else:
                self.instances.append(Instance(self, **instance_latest))
                self.instance_ids.append(instance_latest['id'])

        return self.instances
    
    def get_instance(self, id, retries=0, retry_delay_s=15):
        """ Get a configured `Instance` by id.
        Args:
            id (str): vast.ai instance id.
        Returns:
            Instance
        """
        self.get_instances()
        idx = self.instance_ids.index(id)
        instance = self.instances[idx] if idx >= 0 else None
        if instance is None and retries>0:
            time.sleep(retry_delay_s)
            return get_instance(id, retries=retries-1, retry_delay_s=retry_delay_s)
        return instance

    def get_running_instances(self):
        return [inst for inst in self.get_instances() if inst.status=='running']

    def create_instance(self, offer_id, price=None, disk=1, image="tensorflow/tensorflow:nightly-gpu-py3", 
                        label=None, onstart=None, onstart_cmd=None, jupyter=False, jupyter_dir=None, jupyter_lab=False,
                        lang_utf8=False, python_utf8=False, create_from=None, force=False, raw=True):
        """ Create a new instance given an offer id. 
        Args:
            offer_id (int): Id of offer to launch
            price (float): Per machine bid price in $/h
            disk (float): Size of local disk partition in GB
            image (str): Docker container image to launch
            label (str): Label to set on the instance
            onstart (str): Local filename pointing to file to upload and use as onstart script.
            onstart_cmd (str): Contents of onstart script as single argument
            jupyter (bool): Launch as a jupyter instance instead of an ssh instance. (default: False)
            jupyter_dir (str): For runtype 'jupyter', directory in instance to use to launch jupyter. 
                               Defaults to image's working directory.
            jupyter_lab (bool): Launch instance with jupyter lab (default: False)
            lang_urf8 (bool): Workaround for images with locale problems: install and generate locales 
                              before instance launch, and set locale to C.UTF-8. (default: False)
            python_utf8 (bool): Workaround for images with locale problems: set python's locale to C.UTF-8.
            create_from (str): Existing instance id to use as basis for new instance. Instance configuration 
                               should usually be identical, as only the difference from the base image is copied.
        Raises:
            `vastai.exceptions.ApiKeyNotSet`: if `client.api_key` isn't set. 
        """
        if self.api_key is None: raise ApiKeyNotSet()
        if onstart is not None:
            #if not os.path.isfile(onstart):
            #    raise FileNotFoundError
            with open(onstart, "r") as reader:
                onstart_cmd = reader.read()

        req_url = self._apiurl("/asks/%i/"%offer_id)
        req_json = dict( client_id="me", image=image, price=price, disk=disk, label=label, 
                         onstart=onstart_cmd, runtype="jupyter" if jupyter else "ssh", 
                         python_utf8=python_utf8, lang_utf8=lang_utf8,
                         use_jupyter_lab=jupyter_lab, jupyter_dir=jupyter_dir,
                         create_from=create_from, force=force )
        print(req_url, '\n', json.dumps(req_json))
        resp = requests.put(req_url, json=req_json)
        resp.raise_for_status()
        print(json.dumps(resp.json()))
        resp_data = resp.json()
        # TODO: Add a listener for running status.
        return resp_data

    def search_offers(self, sort_order='score-', query=None, instance_type='on-demand', 
                      no_default=True, disable_bundling=False ):
        """ Search for available machines to bid on. 
        Args:
            order (str): Comma-separated list of fields to sort on. Postfix field with `-` to sort descending.
                         example: `num_gpus,total_flops-` (default='score-')
            instance_type (str): whether to show `bid`(interruptible) or `on-demand` offers. (default: `on-demand`) 
            query (str): Query to search for. default: 'external=false rentable=true verified=true
            storage (float): amount of storage to use for pricing, in GiB. (default: 5.0GiB)
            disable_bundling (bool): Show identical offers. This request is more heavily rate limited. (default: False)
        Raises:
            `vastai.exceptions.ApiKeyNotSet`: if `client.api_key` isn't set. 
        Returns: 
            OfferList: A list of offers
        """
        if self.api_key is None: raise ApiKeyNotSet()
        
        field_alias = dict(cuda_vers = "cuda_max_good", reliability = "reliability2", dlperf_usd = "dlperf_per_dphtotal",
                           dph = "dph_total", flops_usd = "flops_per_dphtotal" )
        if no_default:
            query_args = {}
        else:
            query_args = { "verified":{"eq":True}, "external":{"eq":False}, "rentable":{"eq":True} }

        if query is not None:
            query_args = parse_query(query, query_args)
        #for k,q in query_args.items():
        #    print("%10s: %s"%(k, q));
        order = []
        for name in sort_order.split(","):
            name = name.strip()
            if not name: continue
            direction = "asc"
            if name.strip("-") != name:
                direction = "desc"
            field = name.strip("-");
            if field in field_alias:
                field = field_alias[field];
            order.append([field, direction])

        query_args["order"] = order
        query_args["type"]  = instance_type
        if disable_bundling:
            query_args["disable_bundling"] = True

        req_url = self._apiurl("/bundles", q=query_args)
        resp = requests.get(req_url);
        resp.raise_for_status()
        offer_list = OfferList(resp.json()["offers"])
        return offer_list

    def stop_all_instances(self):
        """ Convenience method to call .stop() on all instances returned by `get_instances`.
        """
        for inst in self.get_instances():
            inst.stop()
        
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


class InstanceList(list):
    """ A list of `Instance`s, returned by `VastClient.get_instances()`
    """
    display_columns = [field[0] for field in instance_fields]
    column_mapper = { field[0]:field[1] for field in instance_fields}
    value_formatters = { field[0]:(field[2],field[3]) for field in instance_fields}
    def as_df(self, columns=None, include_columns=None, exclude_columns=None, 
              rename_columns=True, format_values=True):
        """ Get list as a `pandas.DataFrame`
        Args:
            columns (bool or list of str): Include only the specified columns. 
                If columns is True will show all columns. (default: 
                `InstanceList.display_columns`)
            include_columns (list of str): A list of additional columns names to 
                include in output.
            exclude_columns (list of str): A list of columns names to exclude 
                from output.
            rename_columns (bool or dict of str): Rename data frame columns. If 
                `rename_columns` is a dict will rename with the provided mapping. 
                e.g. `{'id':'host_id'}` renames col `id` to `host_id`.
                If `rename_columns` is True will use the mapping defined in 
                `InstanceList.column_mapper`. 
                If `rename_columns` is False the column names will stay the same.
            format_values (bool): Format values according to the string formatters 
                specified in `instance_fields`.
        """
        if columns is True:
            columns = None # Setting DataFrame `columns=None` returns all columns.
        elif columns is None: #Use the default, InstanceList.display_columns
            columns = self.display_columns
        else: 
            columns = columns
        if type(columns) is list and type(include_columns) is list:
            columns = columns + include_columns
        elif columns is not None and type(columns) is not list:
            raise ValueError("'columns' should be either True, None, or a list of strings. Got '%s' instead."%type(columns))
        # Remove columns in exclude_columns
        if type(columns) is list and type(exclude_columns) is list:
            columns = [c for c in columns if c not in exclude_columns]
        df = pd.DataFrame(self, columns=columns)
        if format_values:
            for k in self.value_formatters.keys():
                fmt = self.value_formatters[k]
                df[k] = [ fmt[0].format( fmt[1](val) if callable(fmt[1]) else val ) if val is not None else 'None'
                        for val in df[k] ]
        if rename_columns is True:
            df = df.rename(columns=self.column_mapper)
        elif type(rename_columns) is dict:
            df = df.rename(columns=rename_columns)
        return df

    def __dict__(self):
        return {i.id:i.__dict__() for i in self}
    def __json__(self):
        return json.dumps([i.__dict__() for i in self])
    def __repr__(self):
        #return self.as_df().to_string(columns=self.column_mapper.values())
        return '\n'.join([inst.__repr__() for inst in self])
        
class OfferList(InstanceList):
    """ A list of Offerss, returned by `VastClient.search_offers()`
    """
    #display_columns = [field[0] for field in displayable_fields]
    #column_mapper = { field[0]:field[1] for field in displayable_fields}
    #value_formatters = { field[0]:(field[2],field[3]) for field in displayable_fields}
    def __repr__(self):
        return '\n'.join(["%s: "%inst['id']+\
               ("Min bid: $%.4f/hr  "%inst['min_bid'] if inst['dph_total']==inst['min_bid'] \
               else "$%.4f/hr  "%inst['dph_total'])+\
               "{inet_up:3.1f}\u2191 {inet_down:3.1f}\u2193  flops:{total_flops:.1f}T  R:{reliability2:.3f}\n"\
               "\t{num_gpus}X {gpu_gb:.1f}GB {gpu_name}, {cpu_cores_effective:.01f}/{cpu_cores}X {cpu_gb:.1f}GB {cpu_name}"\
               .format(gpu_gb=inst['gpu_ram']/1024, cpu_gb=inst['cpu_ram']/2024, **inst)
               for inst in self])

class Instance:
    def __init__(self, client, **kwargs):
        """ Vast.ai Instance, instantiated by `VastClient.get_instances()`.  
            TODO: document Instance attributes
        Args:
            client (VastClient): 
            **kwargs
        """
        self.fields=[]
        self.client = client
        for key in kwargs.keys():
            setattr(self, key, kwargs[key])
            self.fields.append(key)
        self.status = self.actual_status if hasattr(self, 'actual_status') else None
        self._pb_remote = None
        self._ssh_machine = None
        self._tunnels={}

    def __repr__(self):
        """ Uses `pandas.DataTable` for display.
        """
        #return InstanceList([self.__dict__()]).__repr__()
        return "{id}: {actual_status:9s} ${dph_total:.4f}/hr {ssh_host}:{ssh_port}  "\
               "{inet_up:3.1f}\u2191 {inet_down:3.1f}\u2193  flops:{total_flops}T\n"\
               "\t{num_gpus}X {gpu_gb:.1f}GB {gpu_name}, {cpu_cores_effective}/{cpu_cores}X {cpu_gb:.1f}GB {cpu_name}"\
               .format(gpu_gb=self.gpu_ram/1024, cpu_gb=self.cpu_ram/2024, **self.__dict__())+\
               "\n\t%s"%self.status_msg if self.status_msg else ""

    def __dict__(self):
        """ Gets dict of serializable fields.
        """
        return {k:getattr(self,k) for k in self.fields}

    def __json__(self):
        """ Gets JSON serializable string
        """
        return json.dumps(self.__dict__())

#    def get(self, attr, default=None):
#        """ Gets a specified attribute from this Instance. 
#            Used by vastai.vast.display_table.
#        Args:
#            attr (str): Instance attribute
#            default: Default value, if attribute not found. (default: None)
#        """
#        return getattr(self, attr) if hasattr(self, attr) else default
#
    def _request(self, method, url_base, json_data):
        """ Makes http request to `<api_base_url>/instances/<instance.id>/` 
        Args:
            method (str): HTTP request method.
            url_base (str): Request URL, without api_base_url or request params. 
                            e.g. /instances/bid_price/{id}/
            json_data (json): JSON data to send in request body.
        Raises:
            `vastai.exceptions.InstanceError`: if request doesn't return data['success']
        """
        assert type(method) is str
        assert method.lower() in ['get', 'put', 'post', 'update', 'delete']
        url = self.client._apiurl(url_base)
        resp = requests.request(method, url, json=json_data)
        resp.raise_for_status()
        if resp.status_code == 200:
            resp_data = resp.json()
            #if resp_data['success']:
            #    logging.info(json.dumps(resp_data))
            #    return resp_data
            #else:
            #    logging.debug(json.dumps(resp_data))
            #    raise InstanceError(resp_data['msg'], self.id)
        else:
            #logging.debug(resp)
            print("Error:", resp)
            raise InstanceError(resp, self.id)
        return resp_data
        
    @property 
    def ssh_connection_command(self, tunnel_local_port=None, tunnel_remote_port=None):
        """ Convenience method to get ssh command for connecting to this machine. 
            Optionally include params for reverse proxy ssh tunnel. (e.g. to access
            a port behind firewall on the remote machine.
        Args:
            tunnel_local_port (int, optional): local port for ssh tunnel. (default: None)
            tunnel_remote_port (int, optional): remote port for ssh tunnel. 
                                                (default: `tunnel_local_port` or None)
        Returns:
            str: Ssh connection command 
        """
        cmd = "ssh root@%s -p %i -i %s"%(self.ssh_host, self.ssh_port, self.client._get_ssh_key_file())
        if tunnel_local_port:
            cmd += " -L %i:localhost:%i"%(tunnel_local_port, tunnel_remote_port or tunnel_local_port)
        return cmd


    def change_bid(self, price):
        """ Set a new bid price for an interruptible instance.
        Args:
            price (float): per machine bid price in $/hour
        Raises:
            `vastai.exceptions.InstanceError`: if request doesn't return `{'success': true}`
        Returns:
            self
        """
        resp = self._request('put', "/instances/bid_price/%s/"%self.id, {"client_id": "me", "price": price })
        print("Bid changed to $%.3f/hr"%price)
        return self
        
    def start(self):
        """ Starts this configured instance.  
        Raises:
            `vastai.exceptions.InstanceError`: if request doesn't return `{'success': true}`
        Returns:
            self
        """
        self._request('put', "/instances/%s/"%self.id, { "state": "running" })
        print("Starting instance %i."%self.id )
        return self

    def stop(self):
        """ Stops this configured instance. You can restart the instance later. 
        Raises:
            `vastai.exceptions.InstanceError`: if request doesn't return `{'success': true}`
        Returns:
            self
        """
        self._request('put', "/instances/%s/"%self.id, {"state": "stopped"})
        print("Stopping instance %i."%self.id )
        return self

    def destroy(self):
        """ Destroys this configured instance. All data on the remote instance will be lost.
        Raises:
            `vastai.exceptions.InstanceError`: if request doesn't return `{'success': true}`
        Returns:
            None
        """
        self._request('delete', "/instances/%s/"%self.id, {})
        print("Destroying instance %s"%self.id)
            
    def run_command(self, command_str):
        """ Uses paramiko ssh client to execute `command_str` on this remote Instance.
        Args:
            command_str (str): The remote shell command to execute.
        """
        ssh_client = SSHClient()
        ssh_client.set_missing_host_key_policy(AutoAddPolicy)
        print("Connecting to %s:%i "%(self.ssh_host,self.ssh_port))
        try:
            ssh_client.connect(self.ssh_host, port=int(self.ssh_port), username='root', 
                               key_filename=self.client._get_ssh_key_file())
            print("Running command '%s'"%command_str)
            stdin, stdout, stderr = ssh_client.exec_command(command_str)
            print(stdout.read().decode('utf-8'))
            print(stderr.read().decode('utf-8'))
    
        # except NoValidConnectionsError as err:
        #     raise InstanceError(self.id, err.errors)
        finally:
            ssh_client.close()

    @property
    def pb_remote(self):
        """ plumbum ParamikoMachine remote machine
        Returns:
            `plumbum.machines.paramiko_machine.ParamikoMachine`: 
        """
        if self._pb_remote:# and self._pb_remote._session.alive():
            if self._pb_remote._session.alive():
                return self._pb_remote 
        self._pb_remote = ParamikoMachine(self.ssh_host, user='root', port=self.ssh_port, 
                               keyfile=self.client._get_ssh_key_file(), 
                               missing_host_policy=AutoAddPolicy )
        return self._pb_remote

    @property
    def ssh_machine(self):
        """ Returns a `plumbum.machines.SshMachine`, which has a tunnel method """
        #return SshMachine(self.ssh_host, 'root', port=self.ssh_port, keyfile=self.client._get_ssh_key_file())
        if self._ssh_machine:
            if self._ssh_machine._session.alive():
                return self._ssh_machine
        self._ssh_machine = SshMachine(self.ssh_host, 'root', port=self.ssh_port, keyfile=self.client._get_ssh_key_file())
        return self._ssh_machine

    @property
    def _ssh_machine_alive(self):
        if self._ssh_machine is not None:
            #if type(self._ssh_machine) is ClosedRemote:
            #    return False
            #else:
            try:
                return self._ssh_machine._session.alive()
            except ClosedRemoteMachine:
                return False
        return False

    def get_tunnel(self, tunnel_local_port, tunnel_remote_port=None):
        """ Returns a singleton tunnel. 
            Overrides ssh_tunnel.close method to close SshMachine object as well.
        Args:
            tunnel_local_port (int): local port for ssh tunnel. 
            tunnel_remote_port (int, optional): remote port for ssh tunnel. 
                                                (default: `tunnel_local_port`)
        Returns:
            object returned by plumbum.machines.SshMachine.tunnel
        """
        # TODO: Consider closing self.ssh_machine when tunnel is closed.
        if tunnel_remote_port is None: 
            tunnel_remote_port = tunnel_local_port

        if tunnel_local_port in self._tunnels.keys():
            tunnel = self._tunnels[tunnel_local_port]
            if tunnel._session.alive():
                return tunnel
        self._tunnels[tunnel_local_port] = self.ssh_machine.tunnel(tunnel_local_port, tunnel_remote_port)
        return self._tunnels[tunnel_local_port]


    def _wait_until(self, target_status, check_every_s, timeout, destroy_return_delay=20):
        def _check_status(status=target_status):
            if self.status_msg and self.status_msg.startswith("Unhandled setup error"):
                raise(UnhandledSetupError(self.status_msg))
            if self.status is None:
                return False
            if type(status) is str:
                return self.status.lower()==status.lower() 
            elif type(status) is list:
                # Check to see if self.status is any of those listed in status
                for st in status:
                    if _check_status(st):
                        return True
                return False
            else: 
                raise TypeError("Expected target_status to be a string or a list of strings.")

        #self = self.client.get_instance(self.id) # Calls get_instances() to refresh state
        inst_id = self.id
        client = self.client # Keep a reference to client, in case the Instance isn't in get_instances yet
        inst = client.get_instance(inst_id) # Calls get_instances() which refreshes state
        start_time = time.time()
        while not _check_status() and time.time()-start_time<timeout:
            #instance = self.client.get_instance(inst_id)
            inst = client.get_instance(inst_id)
            if inst is None and time.time()-start_time>destroy_return_delay:
                print("Instance destroyed.")
                return 
            #print("Instance %s status is '%s'. Waiting %ss..."%(self.id, self.status, check_every_s))
            print("Waiting %ss..."%(check_every_s))
            time.sleep(check_every_s)
        if _check_status(): 
            return inst

        raise TimeoutError("Checked every %i seconds, but self.status was never in target_status (%s)."%(
                                check_every_s, str(target_status)))

    def wait_until_running(self, check_every_s=60, timeout=600):
        return self._wait_until('running', check_every_s, timeout)

    def wait_until_stopped(self, check_every_s=15, timeout=300):
        return self._wait_until(['exited','stopped'], check_every_s, timeout)

    def wait_until_destroyed(self, check_every_s=10, timeout=60):
        self._wait_until([], check_every_s, timeout)
