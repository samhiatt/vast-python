from . import stubs 
import pytest
import requests_mock
from requests_mock.exceptions import NoMockAddress
import os
import sys, io
from time import sleep

from vastai import vast
from vastai.api import VastClient

from . import stubs
test_api_key = "asupersecretapikey"

@pytest.fixture
def vast_client(requests_mock, monkeypatch, fs):
    fs.create_file("~/.vast_api_key", contents=test_api_key)
    monkeypatch.setenv('VAST_API_KEY', test_api_key)
    client = VastClient()
    assert client.api_key == test_api_key, "Should be using test api key"
    # Add attributes expected by vast.py commands.
    vast_client.url = "https://vast.ai/api/v0"
    vast_client.raw = True
    return client

@pytest.fixture
def instance(vast_client, requests_mock):
    assert vast_client.api_key is not None
    instance = test_get_instances(vast_client, requests_mock)[0]
    assert hasattr(instance,'id'), "instance should have id."
    return instance

def capture_output(func, *args):
    resp = None
    try:
        with io.StringIO() as f:
            sys.stdout = f
            sys.stderr = sys.stdout
            func(*args)
            resp = f.getvalue()
    finally:
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
    return resp


def _compare_requests(requests_mock, vast_func, vast_args, vast_client_method, response_json=None, **kwargs):
    with pytest.raises(NoMockAddress):
        resp = capture_output(vast_func, vast_args)
    print("pytest.py requested: ", requests_mock.last_request.method, requests_mock.last_request.url)
    print("       request body: ", requests_mock.last_request.text)

    # Now test new VastClient.get_instances() and make sure the request matches the one vast.py made.
    last_req = requests_mock.last_request
    requests_mock.request(last_req.method, last_req.url, json=response_json or {})
    result = vast_client_method(**kwargs)

    assert requests_mock.last_request.url == last_req.url, "Request url should be the same as vast.py."
    assert requests_mock.last_request.method == last_req.method, "Request method should be the same as vast.py."
    assert requests_mock.last_request.text == last_req.text, "Request text should be the same as vast.py."

    return result

class VastArgs:
    def __init__(self, **kwargs):
        self.api_key = test_api_key
        self.url = "https://vast.ai/api/v0"
        self.raw = True
        self._keys = ['api_key', 'url', 'raw']
        for k in kwargs:
            setattr(self, k, kwargs[k])
            self._keys.append(k)
    def __dict__(self):
        return {k:getattr(self,k) for k in self._keys}
    def __repr__(self):
        return str(self.__dict__())
    def __iter__(self):
        for k in self._keys:
            yield (k,getattr(self,k))


class LoginArgs(VastArgs):
    def __init__(self, username='john_doe', password='abc123'):
        super().__init__()
        self.api_key = None
        self.username = username
        self.password = password

def test_get_instances(vast_client, requests_mock):
    args = VastArgs()
    instances = _compare_requests(requests_mock, vast.show__instances, args, vast_client.get_instances, 
                                  response_json=stubs.instances_json)
    assert len(instances)==2, "Should have 2 instances from stubs."
    return instances


def test_login(requests_mock, fs):
    assert not fs.exists("~/.vast_api_key"), "API key shouldn't be on mocked filesystem."
    fs.create_dir(os.path.expanduser("~"))

    client = VastClient()
    assert client.api_key is None, "api_key is not set."

    login_opts = LoginArgs()
    _compare_requests(requests_mock, vast.login, login_opts, client.authenticate,
                             response_json=stubs.user_json,
                             username=login_opts.username, password=login_opts.password )

    with open(client.api_key_file) as f:
        assert f.read() == client.api_key, "API key should match the key saved to disk."


def test_instance_start(vast_client, requests_mock, instance):
    args = VastArgs(id=instance.id)
    resp = _compare_requests(requests_mock, vast.start__instance, args, instance.start, 
                             response_json={"success": True})

    
def test_instance_stop(vast_client, requests_mock, instance):
    args = VastArgs(id=instance.id)
    resp = _compare_requests(requests_mock, vast.stop__instance, args, instance.stop, 
                             response_json={"success": True})


def test_instance_destroy(vast_client, requests_mock, instance):
    args = VastArgs(id=instance.id)
    resp = _compare_requests(requests_mock, vast.destroy__instance, args, instance.destroy,
                             response_json={"success": True})


#def test_instance_stop(vast_client, requests_mock, instance):
#    args = VastArgs(id=instance.id)
#    resp = _compare_requests(requests_mock, vast.stop__instance, args, instance.stop,
#                             response_json={"success": True})



