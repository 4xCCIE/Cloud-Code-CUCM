import sys
import logging
from zeep import Client, Settings
from zeep.transports import Transport
from requests import Session
from requests.auth import HTTPBasicAuth
from config import CUCM_HOST, CUCM_USER, CUCM_PASSWORD, WSDL_FILE

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

class CUCMAXL:
    def __init__(self):
        session = Session()
        session.auth = HTTPBasicAuth(CUCM_USER, CUCM_PASSWORD)
        session.verify = False  # For self-signed certs only
        transport = Transport(session=session, timeout=30)
        settings = Settings(strict=False, raw_response=True)
        
        self.client = Client(WSDL_FILE, transport=transport, settings=settings)
        self.service = self.client.create_service(
            '{http://www.cisco.com/AXLAPIService/}AXLAPIBinding',
            f'https://{CUCM_HOST}/axl/'
        )

    def _execute(self, action, **kwargs):
        """Execute an AXL request with error handling"""
        try:
            response = self.service[action](**kwargs)
            return response
        except Exception as e:
            log.error(f"AXL {action} failed: {e}")
            return {"error": str(e)}

    # ----- Phone Operations -----
    def add_phone(self, name, description, product, protocol, device_pool,
                  calling_search_space=None, owner_user_id=None):
        phone = {
            'name': name,
            'description': description,
            'product': self._get_model(product),
            'class': 'Phone',
            'protocol': protocol,
            'protocolSide': 'User',
            'commonPhoneConfigName': 'Standard Common Phone Profile',
            'locationName': 'Hub_None',
            'devicePoolName': device_pool,
            'callingSearchSpaceName': calling_search_space,
            'ownerUserName': owner_user_id,
            'lines': {'line': []}
        }
        return self._execute('addPhone', phone=phone)

    def add_line_to_phone(self, phone_name, line_pattern, route_partition,
                          index=1, alerting_name=None, ascii_alerting_name=None):
        # First add the line (directory number)
        dn = {
            'pattern': line_pattern,
            'routePartitionName': route_partition,
            'usage': 'Device',
            'alertingName': alerting_name,
            'asciiAlertingName': ascii_alerting_name
        }
        line_resp = self._execute('addLine', line=dn)
        # Then associate with phone
        line_assoc = {
            'index': index,
            'dirn': {
                'pattern': line_pattern,
                'routePartitionName': route_partition
            }
        }
        return self._execute('updatePhone', name=phone_name, lines={'line': [line_assoc]})

    def get_phone(self, name):
        return self._execute('getPhone', name=name)

    def update_phone(self, name, **updates):
        return self._execute('updatePhone', name=name, **updates)

    def delete_phone(self, name):
        return self._execute('removePhone', name=name)

    def list_phones(self, criteria=None, returned_tags=None):
        return self._execute('listPhone', searchCriteria=criteria or {},
                             returnedTags=returned_tags or {'name': ''})

    # ----- Line Operations -----
    def add_line(self, pattern, route_partition, description=None, alerting_name=None):
        line = {
            'pattern': pattern,
            'routePartitionName': route_partition,
            'description': description,
            'alertingName': alerting_name
        }
        return self._execute('addLine', line=line)

    def get_line(self, pattern, route_partition):
        return self._execute('getLine', pattern=pattern, routePartitionName=route_partition)

    def update_line(self, pattern, route_partition, **updates):
        return self._execute('updateLine', pattern=pattern,
                             routePartitionName=route_partition, **updates)

    def delete_line(self, pattern, route_partition):
        return self._execute('removeLine', pattern=pattern,
                             routePartitionName=route_partition)

    # ----- User Operations -----
    def add_user(self, user_id, first_name, last_name, password, digest_credentials=None):
        user = {
            'userid': user_id,
            'firstName': first_name,
            'lastName': last_name,
            'password': password,
            'digestCredentials': digest_credentials
        }
        return self._execute('addUser', user=user)

    # ----- Helper Methods -----
    def _get_model(self, product):
        models = {
            '7945': 'Cisco 7945',
            '7965': 'Cisco 7965',
            '8851': 'Cisco 8851',
            '8861': 'Cisco 8861'
        }
        return models.get(product, product)

# ----- Agent Natural Language Handler -----
class Agent:
    def __init__(self):
        self.axl = CUCMAXL()

    def execute(self, user_input):
        """
        Parse natural language and execute appropriate AXL action.
        """
        input_lower = user_input.lower()

        # Add Phone
        if "add phone" in input_lower:
            # Example: "add phone 7945 with name SEP001122334455 in pool Default"
            name = self._extract_param(user_input, "name", "SEP")
            product = self._extract_param(user_input, "phone", "7945")
            device_pool = self._extract_param(user_input, "pool", "Default")
            protocol = self._extract_param(user_input, "protocol", "SIP")
            result = self.axl.add_phone(name, f"Added by agent", product, protocol, device_pool)
            return f"Phone added: {result}"

        # Add Line to Phone
        elif "add line" in input_lower and "to phone" in input_lower:
            # Example: "add line 1001 partition Internal to phone SEP001122334455 at index 1"
            pattern = self._extract_param(user_input, "line", "1000")
            partition = self._extract_param(user_input, "partition", "Internal")
            phone_name = self._extract_param(user_input, "phone", "SEP001122334455")
            index = int(self._extract_param(user_input, "index", "1"))
            result = self.axl.add_line_to_phone(phone_name, pattern, partition, index)
            return f"Line added: {result}"

        # Get Phone
        elif "get phone" in input_lower:
            name = self._extract_param(user_input, "name", "SEP001122334455")
            result = self.axl.get_phone(name)
            return f"Phone details: {result}"

        # Delete Phone
        elif "delete phone" in input_lower:
            name = self._extract_param(user_input, "name", "SEP001122334455")
            result = self.axl.delete_phone(name)
            return f"Phone deleted: {result}"

        # Add User
        elif "add user" in input_lower:
            user_id = self._extract_param(user_input, "userid", "jdoe")
            first = self._extract_param(user_input, "first", "John")
            last = self._extract_param(user_input, "last", "Doe")
            pwd = self._extract_param(user_input, "password", "Cisco123")
            result = self.axl.add_user(user_id, first, last, pwd)
            return f"User added: {result}"

        else:
            return "Unrecognized command. Try: add phone, add line to phone, get phone, delete phone, add user"

    def _extract_param(self, text, key, default):
        """Very basic extraction; can be improved with regex/NER"""
        import re
        patterns = {
            "name": r"name\s+([^\s]+)",
            "phone": r"phone\s+([^\s]+)",
            "pool": r"pool\s+([^\s]+)",
            "line": r"line\s+(\d+)",
            "partition": r"partition\s+([^\s]+)",
            "index": r"index\s+(\d+)",
            "userid": r"userid\s+([^\s]+)",
            "first": r"first\s+([^\s]+)",
            "last": r"last\s+([^\s]+)",
            "password": r"password\s+([^\s]+)",
            "protocol": r"protocol\s+([^\s]+)"
        }
        if key in patterns:
            match = re.search(patterns[key], text, re.IGNORECASE)
            if match:
                return match.group(1)
        return default

if __name__ == "__main__":
    agent = Agent()
    if len(sys.argv) > 1:
        cmd = " ".join(sys.argv[1:])
        print(agent.execute(cmd))
    else:
        print("Usage: python axl.py '<command>'")
        print("Example: python axl.py 'add phone 7945 name SEP001122334455 pool Default'")
