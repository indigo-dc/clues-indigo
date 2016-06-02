import unittest
import mesos
import os
import mock
import json
from clueslib.node import NodeInfo
from clueslib.request import Request
from mock import MagicMock


def read_file(file_name):
    tests_path = os.path.dirname(os.path.abspath(__file__))
    abs_file_path = os.path.join(tests_path, file_name)
    return open(abs_file_path, 'r')


def read_file_as_string(file_name):
    tests_path = os.path.dirname(os.path.abspath(__file__))
    abs_file_path = os.path.join(tests_path, file_name)
    return open(abs_file_path, 'r').read()


def read_file_as_json(file_name):
    return json.loads(read_file_as_string(file_name))


class TestMesosPlugin(unittest.TestCase):

    def test_run_command(self):
        assert mesos.run_command("echo test".split(" ")) == 'test\n'

    @mock.patch('subprocess.Popen.communicate')
    def test_run_command_subprocess_error(self, mock_subprocess):
        mock_subprocess.return_value = ('test', 'error')
        with self.assertRaises(Exception):
            mesos.run_command("echo test".split(" "))

    def test_open_file(self):
        tests_path = os.path.dirname(os.path.abspath(__file__))
        abs_file_path = os.path.join(tests_path, "test-files/mesos-state.json")
        mesos.open_file(abs_file_path)

    def test_open_file_error(self):
        with self.assertRaises(Exception):
            mesos.run_command(mesos.open_file("test"))

    @mock.patch('mesos.run_command')
    def test_curl_command(self, mock_run_command):
        mock_run_command.return_value = read_file_as_string("test-files/mesos-master-tasks.json")
        assert mesos.curl_command(
            "echo test", "test-ip", "error") == read_file_as_json("test-files/mesos-master-tasks.json")

    def test_curl_command_error(self):
        mesos.curl_command("echo test", "test-ip", "Error")

    @mock.patch('mesos.curl_command')
    def test_obtain_mesos_jobs(self, mock_curl_command):
        mock_curl_command.return_value = read_file_as_json("test-files/mesos-master-tasks.json")
        mesos.lrms(MagicMock(mesos.lrms))._obtain_mesos_jobs()
        command = mock_curl_command.call_args[0][0]
        assert command == '/usr/bin/curl -L -X GET http://mesosserverpublic:5050/master/tasks.json'

    @mock.patch('mesos.curl_command')
    def test_obtain_mesos_nodes(self, mock_curl_command):
        mock_curl_command.return_value = read_file_as_json("test-files/mesos-master-slaves.json")
        mesos.lrms(MagicMock(mesos.lrms))._obtain_mesos_nodes()
        command = mock_curl_command.call_args[0][0]
        assert command == '/usr/bin/curl -L -X GET http://mesosserverpublic:5050/master/slaves'

    @mock.patch('mesos.curl_command')
    def test_obtain_mesos_state(self, mock_curl_command):
        mock_curl_command.return_value = read_file_as_json("test-files/mesos-state.json")
        mesos.lrms(MagicMock(mesos.lrms))._obtain_mesos_state()
        command = mock_curl_command.call_args[0][0]
        assert command == '/usr/bin/curl -L -X GET http://mesosserverpublic:5050/master/state.json'

    @mock.patch('mesos.lrms._obtain_mesos_jobs')
    def test_obtain_used_nodes(self, mock_obtain_mesos_jobs):
        mock_obtain_mesos_jobs.return_value = read_file_as_json("test-files/mesos-master-tasks.json")
        assert mesos.lrms(MagicMock(mesos.lrms))._obtain_mesos_used_nodes() == [
            '20150925-075030-1063856798-5050-3482-S0']

    @mock.patch('mesos.lrms._obtain_mesos_jobs')
    def test_obtain_cpu_mem_used(self, mock_obtain_mesos_jobs):
        mesos_tasks = read_file_as_json("test-files/mesos-master-tasks.json")
        mock_obtain_mesos_jobs.return_value = mesos_tasks
        assert mesos.lrms(MagicMock(mesos.lrms))._obtain_cpu_mem_used_in_mesos_node(
            "20150925-075030-1063856798-5050-3482-S0") == (0.5, 536870912)

    def test_infer_clues_node_state_idle(self):
        assert mesos.infer_clues_node_state('1', 'active=false', ['3', '5', 'active=true']) == NodeInfo.IDLE

    def test_infer_clues_node_state_used(self):
        assert mesos.infer_clues_node_state('1', 'active=true', ['1', '2', 'active=true']) == NodeInfo.USED

    def test_infer_clues_node_state_off(self):
        assert mesos.infer_clues_node_state('3', None, ['1', '2', 'active=true']) == NodeInfo.OFF

    def test_infer_clues_job_state_pending(self):
        assert mesos.infer_mesos_job_state('TASK_PENDING') == Request.PENDING

    def test_infer_clues_job_state_attended(self):
        assert mesos.infer_mesos_job_state('TASK_RUNNING') == Request.ATTENDED

    def test_infer_chronos_state_pending(self):
        assert mesos.infer_chronos_job_state('queued') == Request.PENDING

    def test_infer_chronos_state_attended(self):
        assert mesos.infer_chronos_job_state('running') == Request.ATTENDED

    def test_infer_marathon_job_state_attended(self):
        assert mesos.infer_marathon_job_state([1], 1) == Request.ATTENDED

    def test_infer_marathon_job_state_pending(self):
        assert mesos.infer_marathon_job_state([], 0) == Request.PENDING
        assert mesos.infer_marathon_job_state([1], 0) == Request.PENDING
        assert mesos.infer_marathon_job_state([1], None) == Request.PENDING
        assert mesos.infer_marathon_job_state(None, None) == Request.PENDING

    @mock.patch('mesos.lrms._obtain_mesos_nodes')
    @mock.patch('mesos.lrms._obtain_mesos_jobs')
    def test_obtain_chronosjob_node(self, _obtain_mesos_jobs, _obtain_mesos_nodes):
        _obtain_mesos_jobs.return_value = read_file_as_json("test-files/mesos-master-tasks.json")
        _obtain_mesos_nodes.return_value = read_file_as_json("test-files/mesos-master-slaves.json")
        assert mesos.lrms(MagicMock(mesos.lrms))._obtain_chronos_jobs_nodes(
            'dockerjob') == [u'10.0.0.84', u'10.0.0.84', u'10.0.0.84']

    @mock.patch('mesos.curl_command')
    def test_obtain_chronos_jobs(self, mock_curl_command):
        mock_curl_command.return_value = "test_output"
        assert mesos.lrms(MagicMock(mesos.lrms))._obtain_chronos_jobs() == "test_output"

    @mock.patch('mesos.curl_command')
    def test_obtain_chronos_job_state_attended(self, mock_curl_command):
        mock_curl_command.return_value = read_file_as_string("test-files/chronos-state.json")
        assert mesos.lrms(MagicMock(mesos.lrms))._obtain_chronos_job_state('Infinite') == Request.ATTENDED

    @mock.patch('mesos.curl_command')
    def test_obtain_chronos_job_state_pending(self, mock_curl_command):
        mock_curl_command.return_value = read_file_as_string("test-files/chronos-state.json")
        assert mesos.lrms(MagicMock(mesos.lrms))._obtain_chronos_job_state('SAMPLE_JOB1') == Request.PENDING

    @mock.patch('mesos.lrms._obtain_chronos_job_state')
    @mock.patch('mesos.lrms._obtain_mesos_nodes')
    @mock.patch('mesos.lrms._obtain_mesos_jobs')
    @mock.patch('mesos.lrms._obtain_chronos_jobs')
    def test_get_chronos_jobinfolist(self, _obtain_chronos_jobs, _obtain_mesos_jobs,
                                     _obtain_mesos_nodes, _obtain_chronos_job_state):
        # Create patched output return values
        _obtain_chronos_jobs.return_value = read_file_as_json("test-files/chronos-jobs.json")
        _obtain_mesos_jobs.return_value = read_file_as_json("test-files/mesos-master-tasks.json")
        _obtain_mesos_nodes.return_value = read_file_as_json("test-files/mesos-master-slaves.json")
        _obtain_chronos_job_state.return_value = Request.ATTENDED

        job_created = mesos.lrms(MagicMock(mesos.lrms))._get_chronos_jobinfolist()[0]

        # Check the resources and jobs created
        assert job_created.state == Request.ATTENDED
        assert job_created.job_id == 'dockerjob'
        assert job_created.job_nodes_ids == [u'10.0.0.84', u'10.0.0.84', u'10.0.0.84']
        assert job_created.resources.taskcount == 1
        assert job_created.resources.maxtaskspernode == 1
        assert job_created.resources.resources.slots == 0.5
        assert job_created.resources.resources.memory == 268435456
        assert job_created.resources.resources.requests == ['"default" in queues']

    @mock.patch('mesos.calculate_memory_bytes')
    @mock.patch('mesos.lrms._obtain_chronos_job_state')
    @mock.patch('mesos.lrms._obtain_mesos_nodes')
    @mock.patch('mesos.lrms._obtain_mesos_jobs')
    @mock.patch('mesos.lrms._obtain_chronos_jobs')
    def test_get_chronos_jobinfolist_zero_memory(self, _obtain_chronos_jobs, _obtain_mesos_jobs,
                                                 _obtain_mesos_nodes, _obtain_chronos_job_state,
                                                 mock_calculate_memory_bytes):
        # Create patched output return values
        _obtain_chronos_jobs.return_value = read_file_as_json("test-files/chronos-jobs.json")
        _obtain_mesos_jobs.return_value = read_file_as_json("test-files/mesos-master-tasks.json")
        _obtain_mesos_nodes.return_value = read_file_as_json("test-files/mesos-master-slaves.json")
        _obtain_chronos_job_state.return_value = Request.ATTENDED
        mock_calculate_memory_bytes.return_value = -1

        job_created = mesos.lrms(MagicMock(mesos.lrms))._get_chronos_jobinfolist()[0]

        # Check the resources and jobs created
        assert job_created.state == Request.ATTENDED
        assert job_created.job_id == 'dockerjob'
        assert job_created.job_nodes_ids == [u'10.0.0.84', u'10.0.0.84', u'10.0.0.84']
        assert job_created.resources.taskcount == 1
        assert job_created.resources.maxtaskspernode == 1
        assert job_created.resources.resources.slots == 0.5
        assert job_created.resources.resources.memory == 536870912
        assert job_created.resources.resources.requests == ['"default" in queues']

    @mock.patch('mesos.curl_command')
    def test_obtain_marathon_jobs(self, curl_command):
        curl_command.return_value = "test_output"
        assert mesos.lrms(MagicMock(mesos.lrms))._obtain_marathon_jobs() == "test_output"

    @mock.patch('mesos.lrms._obtain_marathon_jobs')
    def test_get_marathon_jobinfolist(self, _obtain_marathon_jobs):
        # Create patched output return values
        _obtain_marathon_jobs.return_value = read_file_as_json("test-files/marathon-jobs.json")
        job_created = mesos.lrms(MagicMock(mesos.lrms))._get_marathon_jobinfolist()[0]

        assert job_created.state == Request.ATTENDED
        assert job_created.job_id == '/babbo'
        assert job_created.job_nodes_ids == [u'vnode1']
        assert job_created.resources.taskcount == 1
        assert job_created.resources.maxtaskspernode == 1
        assert job_created.resources.resources.slots == 1.0
        assert job_created.resources.resources.memory == 16777216
        assert job_created.resources.resources.requests == ['"default" in queues']

    @mock.patch('mesos.calculate_memory_bytes')
    @mock.patch('mesos.lrms._obtain_marathon_jobs')
    def test_get_marathon_jobinfolist_zero_memory(self, _obtain_marathon_jobs, mock_calculate_memory_bytes):
        # Create patched output return values
        _obtain_marathon_jobs.return_value = read_file_as_json("test-files/marathon-jobs.json")
        mock_calculate_memory_bytes.return_value = -1
        job_created = mesos.lrms(MagicMock(mesos.lrms))._get_marathon_jobinfolist()[0]

        assert job_created.state == Request.ATTENDED
        assert job_created.job_id == '/babbo'
        assert job_created.job_nodes_ids == [u'vnode1']
        assert job_created.resources.taskcount == 1
        assert job_created.resources.maxtaskspernode == 1
        assert job_created.resources.resources.slots == 1.0
        assert job_created.resources.resources.memory == 536870912
        assert job_created.resources.resources.requests == ['"default" in queues']

    def test_init_lrms_empty(self):
        lrms = mesos.lrms()
        assert lrms._server_ip == 'mesosserverpublic'
        assert lrms._nodes == '/usr/bin/curl -L -X GET http://mesosserverpublic:5050/master/slaves'
        assert lrms._state == '/usr/bin/curl -L -X GET http://mesosserverpublic:5050/master/state.json'
        assert lrms._jobs == '/usr/bin/curl -L -X GET http://mesosserverpublic:5050/master/tasks.json'
        assert lrms._marathon == '/usr/bin/curl -L -X GET http://mesosserverpublic:8080/v2/apps?embed=tasks'
        assert lrms._chronos == '/usr/bin/curl -L -X GET http://mesosserverpublic:4400/scheduler/jobs'
        assert lrms._chronos_state == '/usr/bin/curl -L -X GET http://mesosserverpublic:4400/scheduler/graph/csv'
        assert lrms.get_id() == 'MESOS_mesosserverpublic'

    def test_init_lrms(self):
        lrms = mesos.lrms('test_ip', 'nodes', 'state', 'jobs', 'marathon', 'chronos', 'chronos_state')
        assert lrms._server_ip == 'test_ip'
        assert lrms._nodes == 'nodes'
        assert lrms._state == 'state'
        assert lrms._jobs == 'jobs'
        assert lrms._marathon == 'marathon'
        assert lrms._chronos == 'chronos'
        assert lrms._chronos_state == 'chronos_state'
        assert lrms.get_id() == 'MESOS_test_ip'

    @mock.patch('mesos.lrms._obtain_mesos_jobs')
    @mock.patch('mesos.lrms._obtain_mesos_nodes')
    @mock.patch('mesos.open_file')
    def test_get_nodeinfolist(self, open_file, _obtain_mesos_nodes, _obtain_mesos_jobs):
        open_file.return_value = read_file("test-files/mesos_vnodes.info")
        _obtain_mesos_nodes.return_value = read_file_as_json("test-files/mesos-master-slaves.json")
        _obtain_mesos_jobs.return_value = read_file_as_json("test-files/mesos-master-tasks.json")

        nodeinfolist = mesos.lrms(MagicMock(mesos.lrms)).get_nodeinfolist()
        if nodeinfolist:
            result = '[NODE "10.0.0.84"] state: used, 0/1 (free slots), 116391936/653262848 (mem)'
            assert str(nodeinfolist['10.0.0.84']) == result
            result = '[NODE "vnode2"] state: off, 1/1 (free slots), 1572864000/1572864000 (mem)'
            assert str(nodeinfolist['vnode2']) == result

    @mock.patch('mesos.lrms._obtain_chronos_job_state')
    @mock.patch('mesos.lrms._obtain_chronos_jobs')
    @mock.patch('mesos.lrms._obtain_mesos_jobs')
    @mock.patch('mesos.lrms._obtain_marathon_jobs')
    @mock.patch('mesos.lrms._obtain_mesos_nodes')
    @mock.patch('mesos.lrms._obtain_mesos_state')
    def test_get_jobinfolist(self, _obtain_mesos_state, _obtain_mesos_nodes, _obtain_marathon_jobs,
                             _obtain_mesos_jobs, _obtain_chronos_jobs, _obtain_chronos_job_state):
        _obtain_mesos_state.return_value = read_file_as_json("test-files/mesos-state.json")
        _obtain_mesos_nodes.return_value = read_file_as_json("test-files/mesos-master-slaves.json")
        _obtain_marathon_jobs.return_value = read_file_as_json("test-files/marathon-jobs.json")
        _obtain_mesos_jobs.return_value = read_file_as_json("test-files/mesos-master-tasks.json")
        _obtain_chronos_jobs.return_value = read_file_as_json("test-files/chronos-jobs.json")
        _obtain_chronos_job_state.return_value = Request.ATTENDED
        job_info_list = mesos.lrms(MagicMock(mesos.lrms)).get_jobinfolist()

        assert len(job_info_list) == 4

if __name__ == '__main__':
    unittest.main()
