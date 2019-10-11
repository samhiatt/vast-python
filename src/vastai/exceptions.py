class APIError(Exception):
    def __init__(self, instance_id, message=''):
        super().__init__("Instance %s\n%s"%(instance_id, message))

class UserNotAuthenticated(Exception):
    def __init__(self, message):
        super().__init__(message+"\nMust provide a valid api_key or login with username/password.")

class PrivateSshKeyNotFound(Exception):
    def __init__(self, key_dir, pub_key):
        super().__init__(
            "Could not find ssh key in %s matching public key:\n%s"%(
            key_dir,pub_key)
        )
