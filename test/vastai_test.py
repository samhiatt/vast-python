from vastai.api import VastClient, api_base_url, default_api_key_file
from vastai.exceptions import Unauthorized
from . import stubs 
import pytest
import requests_mock
from requests_mock.exceptions import NoMockAddress
import os, tempfile

test_api_key = "asupersecretapikey"

@pytest.fixture
def api_key_file(tmpdir):
  temp_file = tmpdir.join("vast_api_key")
  yield str(temp_file)
  print("Cleaning up "+str(temp_file))
  tmpdir.remove()

  #temp_filename = os.path.join(tempfile.tempdir, "vastai_"+next(tempfile._get_candidate_names()))
  #yield temp_filename
  #os.remove(temp_filename)
  #print("Removed %s."%temp_filename)

@pytest.fixture
def authorized_client(requests_mock, api_key_file):
  assert not os.path.exists(api_key_file), "api key file shouldn't exist yet"
  json_data = {"id": 1234, "api_key": test_api_key, "username": "john_doe",
               "ssh_key": "ssh-rsa AAAA..."}
  requests_mock.put(api_base_url+"/users/current/", json=json_data )
  new_client = VastClient(api_key_file=api_key_file)
  assert type(new_client) is VastClient,    "Should be a VastClient object."
  assert new_client.api_key is None, "Shouldn't have an api_key yet."
  retVal = new_client.authenticate('john_doe','abc123')
  assert retVal is new_client, "Client.authenticate should return self."
  assert new_client.api_key == test_api_key
  assert requests_mock.last_request.json() == {'username': 'john_doe', 'password': 'abc123'}
  check_attrs(new_client, json_data)
  assert os.path.exists(api_key_file), "Should have created api key file."
  with open(api_key_file) as f:
    assert f.read()==new_client.api_key, "Saved API key should match client.api_key."
  return new_client

@pytest.fixture
def instance(requests_mock, authorized_client):
  requests_mock.get(api_base_url+"/instances?api_key=%s"%test_api_key, 
                    json=stubs.instances_json)
  return authorized_client.get_instances()[0]

def test_default_api_key_file(fs):
  client = VastClient()
  assert client.api_key_file == default_api_key_file, \
         "api_key_file should default to %s"%default_api_key_file
  client = VastClient(api_key_file=None)
  assert client.api_key_file is None, "client.api_key_file should still be None."

def test_bad_login(requests_mock, fs):
  requests_mock.put(api_base_url+"/users/current/", status_code=401, reason='Unauthorized' )
  client = VastClient()
  assert client.api_key_file == default_api_key_file
  with pytest.raises(Unauthorized):
    retVal = client.authenticate('aFakeUser','badPassword')
    assert retVal.api_key is None
  assert requests_mock.last_request.json() == {'username': 'aFakeUser', 'password': 'badPassword'}

def test_api_key_env_var(requests_mock, monkeypatch):
  monkeypatch.setenv('VAST_API_KEY', test_api_key)
  client = VastClient()
  assert client.api_key == test_api_key, "api_key should be set from VAST_API_KEY env var."
  requests_mock.get(api_base_url+"/users/current/?api_key=%s"%(client.api_key), json=stubs.user_json)
  client.authenticate()
  check_attrs(client, stubs.user_json)

#@pytest.fixture
#def fs_mocker(fs):
#  # Mock the default api_key_file directory.
#  fs.create_dir(os.path.dirname(default_api_key_file))
#  print("Created mock dir: "+os.path.dirname(default_api_key_file))
#  return fs

def test_username_password_env_vars(requests_mock, monkeypatch, fs):
  """ Tests authentication with username and password set in environment variables. 
  Params:
      requests_mock: Network request mocker.
      monkeypatch: Used for mocking env variables.
      fs: pyfakefs plugin for mocking filesystem operations.
  """
  monkeypatch.setenv('VAST_USERNAME','john_doe')
  monkeypatch.setenv('VAST_PASSWORD','abc123')
  client = VastClient()
  assert client.api_key_file == default_api_key_file, "api_key_file location should default to home dir."
  assert client.api_key is None, "api_key shouldn't be set yet."
  requests_mock.put(api_base_url+"/users/current/", json=stubs.user_json)
  fs.create_dir(os.path.dirname(default_api_key_file))
  client.authenticate()
  assert client.api_key_file == default_api_key_file
  with open(client.api_key_file) as f:
    assert f.read() == client.api_key, "Contents of %s should match client.api_key"%default_api_key_file
  check_attrs(client, stubs.user_json)
  assert client.api_key == test_api_key, "Retrieved api key should match test_api_key."

def test_authentication_with_api_key_file(requests_mock, authorized_client):
  assert os.path.exists(authorized_client.api_key_file), "api_key_file should exist."
  json_data = {"id": 1234, "username": "john_doe", "ssh_key": "ssh-rsa AAAA..."}
  requests_mock.get(api_base_url+"/users/current/?api_key=%s"%(authorized_client.api_key), json=json_data)
  new_client = VastClient(api_key_file=authorized_client.api_key_file)
  assert new_client.api_key is not None, "new_client.api_key should be set."
  assert new_client.api_key == authorized_client.api_key, \
         "new_client.api_key should match authorized_client.api_key."
  new_client.authenticate()
  assert new_client.api_key == authorized_client.api_key
  check_attrs(new_client, json_data)

def test_get_instances(requests_mock, authorized_client):
  requests_mock.get(api_base_url+"/instances?api_key=%s"%test_api_key, 
      json=stubs.instances_json)
  instances = authorized_client.get_instances()
  #log_request(requests_mock.last_request)
  assert len(instances) == 2
    
def test_get_instance(requests_mock, authorized_client):
  requests_mock.get(api_base_url+"/instances?api_key=%s"%test_api_key, 
      json=stubs.instances_json)
  instance = authorized_client.get_instance(384792)
  check_attrs(instance, stubs.instances_json['instances'][0])
  return instance
    
def test_start_instance(requests_mock, instance):
  requests_mock.put(api_base_url+"/instances/%s/?api_key=%s"%(instance.id, test_api_key), 
      json={"success": True})
  instance.start()
  #log_request(requests_mock.last_request)
  assert requests_mock.last_request.method == 'PUT'
  assert requests_mock.last_request.body == b'{"state": "running"}'
    
def test_stop_instance(requests_mock, instance):
  requests_mock.put(api_base_url+"/instances/%s/?api_key=%s"%(instance.id, test_api_key), 
      json={"success": True})
  instance.stop()
  #log_request(requests_mock.last_request)
  assert requests_mock.last_request.method == 'PUT'
  assert requests_mock.last_request.body == b'{"state": "stopped"}'
    
def test_destroy_instance(requests_mock, instance):
  requests_mock.delete(api_base_url+"/instances/%s/?api_key=%s"%(instance.id, test_api_key), 
      json={"success": True})
  instance.destroy()
  #log_request(requests_mock.last_request)
  assert requests_mock.last_request.method == 'DELETE'

def test_instance_repr(instance):
  assert instance.__repr__().strip() == stubs.instance_repr.strip()

def test_instance_json(instance):
  assert type(instance.__json__()) is str, "Should produce a string without raising an error."
  
def test_get_ssh_key(fs):
  # TODO
  pass
  
def check_attrs(obj, attr_dict):
  """ Checks that all keys in attr_dict exist on obj, 
      and that their corresponding values are equal.
  """
  for attr in attr_dict:
    assert getattr(obj, attr) == attr_dict[attr], \
           "%s.%s should be '%s'"%(type(obj), attr, attr_dict[attr])

#def log_request(request, include_headers=False):
#  print(request.method, request.url, request.body)
#  if include_headers: print(request.headers)
#  assert True
