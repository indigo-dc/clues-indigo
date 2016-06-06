import unittest
import os
import mock
from indigo_orchestrator import powermanager
from mock import MagicMock, patch

def read_file_as_string(file_name):
    tests_path = os.path.dirname(os.path.abspath(__file__))
    abs_file_path = os.path.join(tests_path, file_name)
    return open(abs_file_path, 'r').read()

class TestMesosPlugin(unittest.TestCase):

    def test_powermanager_Task(self):
        task = powermanager.Task(powermanager.POWER_ON, 'test')
        assert task.nname == 'test'
        assert task.operation == powermanager.POWER_ON
        
    def test_powermanager_Task_cmp(self):
        task1 = powermanager.Task(powermanager.POWER_ON, 'test')
        task2 = powermanager.Task(powermanager.POWER_ON, 'test')
        task3 = powermanager.Task(powermanager.POWER_OFF, 'test')
        assert task1.__cmp__(task2) == 0
        assert task1.__cmp__(task3) == -1
        
    def test_powermanager_Task_str(self):
        task1 = powermanager.Task(powermanager.POWER_OFF, 'test')
        assert str(task1) == 'Power Off on test'
        task2 = powermanager.Task(powermanager.POWER_ON, 'test')
        assert str(task2) == 'Power On on test'        
        
    @patch('cpyutils.eventloop.now')        
    def test_powermanager_VmNode(self, mock_timer):
        mock_timer.return_value = 5
        vm = powermanager.VM_Node(1)
        assert vm.vm_id == 1
        assert vm.timestamp_recovered == 0
        assert vm.timestamp_created == 5
        assert vm.timestamp_seen == 5
        
    def test_powermanager_get_auth_header(self):
        mock_pm = MagicMock(powermanager)
        mock_pm._auth_data = {'username':'paco', 'password':'12345'}
        assert powermanager._get_auth_header(mock_pm) == {'Authorization': 'Basic cGFjbzoxMjM0NQ=='}

    def test_powermanager_power_on(self):
        mock_pm = MagicMock(powermanager)
        mock_pm._mvs_seen = ["test1","test2","test3"]
        mock_pm._INDIGO_ORCHESTRATOR_MAX_INSTANCES = 5
        assert powermanager.power_on(mock_pm, "test5") == (True, 'test5')
        
    def test_powermanager_power_on_max_vm(self):
        mock_pm = MagicMock(powermanager)
        mock_pm._mvs_seen = ["test1","test2","test3"]
        mock_pm._INDIGO_ORCHESTRATOR_MAX_INSTANCES = 1
        assert powermanager.power_on(mock_pm, "test2") == (False, 'test2')

    def test_powermanager_power_on_vm_exists(self):
        mock_pm = MagicMock(powermanager)
        mock_pm._mvs_seen = ["test1","test2","test3"]
        mock_pm._INDIGO_ORCHESTRATOR_MAX_INSTANCES = 5
        assert powermanager.power_on(mock_pm, "test2") == (True, 'test2')

    def get_resources_page(self, page=0):
        return 200, read_file_as_string("test-files/orchestrator-resources-p%d.json" % page)

    @mock.patch('cpyutils.eventloop.now')
    @mock.patch('cpyutils.db.DB.create_from_string')
    @mock.patch('indigo_orchestrator.powermanager._create_db')
    @mock.patch('indigo_orchestrator.powermanager._load_pending_tasks')
    @mock.patch('indigo_orchestrator.powermanager._load_mvs_seen')
    @mock.patch('indigo_orchestrator.powermanager._get_resources_page')
    def test_get_vms(self, get_resources_page, load_mvs_seen, load_pending_tasks, create_db, cpyutils_db_create, now):
        now.return_value = 1.0
        create_db.return_value = True
        load_mvs_seen.return_value = {'vnode1': powermanager.VM_Node('ee6a8510-974c-411c-b8ff-71bb133148eb')}
        load_pending_tasks.return_value = []
        cpyutils_db_create.return_value = None
        #get_resources_page.return_value = 200, read_file_as_string("test-files/orchestrator-resources.json")
        get_resources_page.side_effect = self.get_resources_page
        vms = powermanager()._get_vms()
        assert vms["vnode1"].timestamp_seen == 1.0

if __name__ == '__main__':
    unittest.main()
