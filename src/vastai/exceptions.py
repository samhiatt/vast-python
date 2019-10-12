class InstanceError(Exception):
    def __init__(self, message='', instance_id=None):
        super().__init__("Error making request for Instance %s\n%s"%(instance_id, message))

class Unauthorized(Exception):
    def __init__(self, message):
        super().__init__(message+"\nMust provide a valid api_key or login with username/password.")
        
class ApiKeyNotSet(Exception):
    def __init__(self):
        super().__init__("Vast.ai API key not set. Set by calling login, setting VAST_API_KEY "+\
                         "env variable, or specifying path to .vast_api_key file.")

class PrivateSshKeyNotFound(Exception):
    def __init__(self, key_dir, pub_key):
        super().__init__(
            "Could not find ssh key in %s matching public key:\n%s"%(
            key_dir,pub_key)
        )
