CLUES INDIGO Extensions
=========================
CLUES is an elasticity manager system for HPC clusters and Cloud infrastructures that features the ability to power on/deploy working nodes as needed (depending on the job workload of the cluster) and to power off/terminate them when they are no longer needed. CLUES is available at the [grycap/clues](https://github.com/grycap/clues) GitHub repository.

CLUES has been extended in the INDIGO-DataCloud project with new plugins to support the [PaaS Orchestrator](https://github.com/indigo-dc/orchestrator) and to introduce elasticity capabilities to both HTCondor and Apache Mesos (including its frameworks Chronos and Marathon).

Therefore, this repository includes the following plugins:

* indigo_orchestrator.py: CLUES plugin to connect with the INDIGO orchestrator. Copy it to the ``cluesplugins`` directory of CLUES.
* condor.py: CLUES plugin to connect with the HTCondor.
* mesos.py:  CLUES plugin to connect with the Mesos, Chronos, and Marathon.
