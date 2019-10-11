from vastai.api import User
from vastai.exceptions import UserNotAuthenticated
from .stubs import instances_json
import pytest
import requests_mock
from requests_mock.exceptions import NoMockAddress
import os

def test_bad_login(requests_mock):
  requests_mock.put("https://vast.ai/api/v0/users/current/", status_code=401, 
                    reason='Unauthorized' )
  user = User(api_key_file=None)
  assert user.api_key_file is None
  with pytest.raises(UserNotAuthenticated):
    retVal = user.login('aFakeUser','badPassword')
    assert retVal.api_key is None
  assert requests_mock.last_request.json() == {'username': 'aFakeUser', 'password': 'badPassword'}

def test_login(requests_mock):
  test_api_key = "asupersecretapikey"
  requests_mock.put("https://vast.ai/api/v0/users/current/", 
    json={"id": 1234, "api_key": test_api_key, "username": "aFakeLogin", 
          "ssh_key": "ssh-rsa AAAA..."},
  )
  test_api_key_file = '/tmp/test_api_key.txt'
  if os.path.exists(test_api_key_file): os.remove(test_api_key_file)
  user = User(api_key_file=test_api_key_file)
  assert user.api_key is None, "Shouldn't have an api_key yet."
  assert type(user.api_key_file) is str
  assert user.api_key_file == '/tmp/test_api_key.txt'
  retVal = user.login('aFakeLogin','abc123')
  assert retVal is user
  assert user.api_key == test_api_key
  assert requests_mock.last_request.json() == {'username': 'aFakeLogin', 'password': 'abc123'}
  assert os.path.exists(test_api_key_file)
  assert user.id == 1234, "user id should be set from login response."
  with open(test_api_key_file) as f:
    assert f.read()==test_api_key
  os.remove(test_api_key_file)
  return user
        
def test_get_user_with_api_key(requests_mock):
  test_api_key = "asupersecretapikey"
  requests_mock.get("https://vast.ai/api/v0/users/current/?api_key=%s"%(test_api_key), 
        json={"id": 1234, "username": "aFakeLogin", "ssh_key": "ssh-rsa AAAA..."})
  user = User(api_key=test_api_key).login()
  assert user.id == 1234
  assert user.username == 'aFakeLogin'
  return user

def test_get_instances(requests_mock):
  test_api_key = "asupersecretapikey"
  requests_mock.get("https://vast.ai/api/v0/instances?api_key=%s"%test_api_key, 
      json=instances_json)
  user = test_get_user_with_api_key(requests_mock)
  assert user.id is not None
  instances = user.get_instances()
  log_request(requests_mock.last_request)
  assert len(instances) == 2
  return instances
    
def test_get_instance(requests_mock):
  # instances = test_get_instances(requests_mock)
  test_api_key = "asupersecretapikey"
  user = test_get_user_with_api_key(requests_mock)
  requests_mock.get("https://vast.ai/api/v0/instances?api_key=%s"%test_api_key, 
      json=instances_json)
  instance = user.get_instance(384792)
  log_request(requests_mock.last_request)
  assert instance.id == 384792
  assert instance.status == 'exited'
  assert instance.gpu_name == 'GTX 1080 Ti'
  # ID: 384792, Status: exited, Model: GTX 1080 Ti, GPUs: 2X, vCPUs: 8X, RAM: 16.0, Storage: 1, Cost: $0.2202/hr, Net up: 23.7, Net down: 68.7, Reliability: 99.6, Days Remaining: 23.3,
  return instance
    
def test_start_instance(requests_mock):
  test_api_key = "asupersecretapikey"
  instances = test_get_instances(requests_mock)
  instance = instances[0] 
  assert instance.id == 384792
  requests_mock.put("https://vast.ai/api/v0/instances/%s/?api_key=%s"%(instance.id, test_api_key), 
      json={"success": True})
  retVal = instance.start()
  log_request(requests_mock.last_request)
  assert requests_mock.last_request.method == 'PUT'
  assert requests_mock.last_request.body == b'{"state": "running"}'
  assert retVal is instance
    
def test_stop_instance(requests_mock):
  test_api_key = "asupersecretapikey"
  instances = test_get_instances(requests_mock)
  instance = instances[0] 
  assert instance.id == 384792
  requests_mock.put("https://vast.ai/api/v0/instances/%s/?api_key=%s"%(instance.id, test_api_key), 
      json={"success": True})
  retVal = instance.stop()
  log_request(requests_mock.last_request)
  assert requests_mock.last_request.method == 'PUT'
  assert requests_mock.last_request.body == b'{"state": "stopped"}'
  assert retVal is instance
    
def test_destroy_instance(requests_mock):
  test_api_key = "asupersecretapikey"
  instances = test_get_instances(requests_mock)
  instance = instances[0] 
  assert instance.id == 384792
  requests_mock.delete("https://vast.ai/api/v0/instances/%s/?api_key=%s"%(instance.id, test_api_key), 
      json={"success": True})
  retVal = instance.destroy()
  log_request(requests_mock.last_request)
  assert requests_mock.last_request.method == 'DELETE'
  assert retVal is instance
  
  
def log_request(request, include_headers=False):
  print(request.method, request.url, request.body)
  if include_headers: print(request.headers)

