import unittest
from + import powermanager
from mock import MagicMock, patch

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
        

if __name__ == '__main__':
    unittest.main()
