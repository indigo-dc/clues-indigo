import unittest
from indigo_orchestrator import powermanager
from mock import MagicMock

class TestMesosPlugin(unittest.TestCase):

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
