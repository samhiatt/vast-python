# vast-python

Python interface to vast.ai API.

This project includes and is based on the vast.ai command-line interface [vast-ai/vast-python:vast.py](https://github.com/vast-ai/vast-python/blob/0f0c6b84e689dd9b1bfaf78c8bfda419d8ef9711/vast.py) and is intended to provided an object-oriented python interface to vast.ai resources. It also provides some useful helper methods to run remote commands on running vast.ai Instances.

Functionality is currently incomplete, but should be enough to:
* Log in
    * Stores user's API key in `~/.vast_api_key` by default.
* Get current list of configured vast.ai Instances
* Start a configured Instance
* Stop a running Instance
* Destroy an Instance

Creating a new instance is not yet supported using the python api. If you'd like to create a new instance that this API can interact with, use the [web-based console](https://vast.ai/console/create/).

Currently no functionality is implemented for hosting machines. 


## Installation

`pip install git+https://github.com/samhiatt/vast-python`

## Documentation

Documentation is automatically generated using [pdoc](https://pdoc3.github.io/pdoc/) and is hosted at https://samhiatt.github.io/vast-python/.

## Usage

Login to vast.ai with user credentials.
```python
from vastai.api import VastClient

user = VastClient().authenticate('john_doe')
```
Opens a prompt for password.
```
Password: ________
Saving api_key to /home/john_doe/.vast_api_key.
```

Once `~/.vast_api_key` has been set `username` and `password` are no longer needed for authentication. 
```python
user = VastClient().authenticate()  # Providing username e.g. VastClient().authenticate('john_doe') still works.
```
```
Initializing user with api_key from /home/john_doe/.vast_api_key.
```

Get the user's configured instances.
```python
user.get_instances()
```
```
[Model: RTX 2080 Ti, ID: 363020, Net down: 147.2, Days Remaining: 41.6, Cost: $0.2302/hr, Storage: 1GB, Net up: 32.3, GPUs: 1X, RAM: 128.8, vCPUs: 6X, Status: exited, Reliability: 99.7,
 Model: GTX 1070 Ti, ID: 365316, Net down: 312.2, Days Remaining: 17.4, Cost: $0.0804/hr, Storage: 1GB, Net up: 309.6, GPUs: 1X, RAM: 32.0, vCPUs: 4X, Status: exited, Reliability: 97.6,
 Model: GTX 1070 Ti, ID: 365317, Net down: 312.2, Days Remaining: 17.4, Cost: $0.0804/hr, Storage: 1GB, Net up: 309.6, GPUs: 1X, RAM: 32.0, vCPUs: 4X, Status: exited, Reliability: 97.6]
```

Get a specific instance by id. 
```python
instance=user.get_instance(365317)
instance
```
```
ID: 365317, Status: exited, vCPUs: 4X, Storage: 1GB, Cost: $0.0804/hr, RAM: 32.0, Days Remaining: 19.6, Net down: 313.0, Net up: 304.9, GPUs: 1X, Reliability: 97.5, Model: GTX 1070 Ti
```

Get all the instance attributes as a python dict:
```python
print(instance.__dict__())
```
```
{'gpu_ram': 8119, 'cuda_max_good': 10.0, 'end_date': 1572262468.0, 'gpu_mem_bw': 189.5, 'pcie_bw': 12.5, 'inet_down_cost': 0.1, 'host_id': 115, 'cpu_cores_effective': 4.0, 'ssh_port': 15317, 'status_msg': 'Successfully loaded tensorflow/tensorflow:nightly-gpu-py3', 'actual_status': 'exited', 'has_avx': 1, 'pci_gen': 3.0, 'inet_down': 312.2, 'gpu_lanes': 16, 'flops_per_dphtotal': 115.582106812386, 'inet_down_billed': 3715.402344, 'dph_total': 0.0804199218749999, 'image_runtype': 'ssh', 'image_args': [], 'storage_cost': 4.0, 'num_gpus': 1, 'driver_version': '410.78', 'dph_base': 0.0749999999999999, 'min_bid': 0.090125, 'is_bid': False, 'inet_up_billed': 1299.050781, 'duration': 1504431.46089625, 'reliability2': 0.9762622, 'gpu_name': 'GTX 1070 Ti', 'storage_total_cost': 0.005419921875, 'start_date': 1563920386.97885, 'dlperf': None, 'disk_space': 0.9755859375, 'inet_up': 309.6, 'gpu_display_active': False, 'dlperf_per_dphtotal': None, 'ssh_host': 'ssh5.vast.ai', 'bundle_id': None, 'disk_bw': 2478.52220648348, 'machine_id': 940, 'cur_state': 'stopped', 'ssh_idx': '5', 'rentable': True, 'disk_name': 'KINGSTON', 'next_state': 'stopped', 'jupyter_token': 'f09046a39f4de185ed89dd587c6b48b23c7e88cc3575b2b6ce36b3d506ab3737', 'id': 365317, 'external': False, 'webpage': None, 'intended_status': 'stopped', 'total_flops': 9.295104, 'mobo_name': 'X399 Taichi', 'image_uuid': 'tensorflow/tensorflow:nightly-gpu-py3', 'inet_up_cost': 0.1, 'gpu_temp': 32.0, 'label': None, 'cpu_name': 'AMD Ryzen Threadripper 1900X 8-Core Processor', 'gpu_frac': 0.25, 'cpu_cores': 16, 'logo': '/static/logos/vastai_small2.png', 'compute_cap': 610, 'gpu_util': 0.0, 'cpu_ram': 32028}
```

Start a stopped instance.
```python
instance.start()
```
```
Starting instance 365317.
```

Run a remote command on an Instance over ssh.
```python
instance.run_command('pip install --upgrade pip')
```
```
Connecting to ssh5.vast.ai:15317 
Running command 'pip install --upgrade pip'
Requirement already up-to-date: pip in /usr/local/lib/python3.6/dist-packages (19.2.3)
```
This connects to the instance over SSH using the ssh key detected by `user.get_ssh_key_file()`. 

`get_ssh_key_file()` looks for a public ssh key matching the ssh key provided in the vast.ai console and returns the file name corresponding to the private ssh key used to connect to running instances. If this key is not found it will raise an error.  
```python
user.get_ssh_key_file()
```
```
---------------------------------------------------------------------------
PrivateSshKeyNotFound                     Traceback (most recent call last)
<ipython-input-20-0bf791de7402> in <module>
----> 1 user.get_ssh_key_file()

~/Downloads/vast-python/src/vastai/api.py in get_ssh_key_file(self, key_dir)
    131                     if f.read().strip()==self.ssh_key.strip():
    132                         return pub_key_file[:-4]
--> 133         raise PrivateSshKeyNotFound(key_dir, self.ssh_key)
    134 
    135     def get_instance(self, id):

PrivateSshKeyNotFound: Could not find ssh key in /home/john_doe/.ssh/ matching public key: ...
```


Stop a running instance.
```python
instance.stop()
```
```
Stopping instance 365317.
```


