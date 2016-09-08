CLUES INDIGO Extensions
=========================
CLUES is an elasticity manager system for HPC clusters and Cloud infrastructures that features the ability to power on/deploy working nodes as needed (depending on the job workload of the cluster) and to power off/terminate them when they are no longer needed. CLUES is available at the [grycap/clues](https://github.com/grycap/clues) GitHub repository.

CLUES has been extended in the INDIGO-DataCloud project with new plugins to support the [PaaS Orchestrator](https://github.com/indigo-dc/orchestrator) and to introduce elasticity capabilities to both HTCondor and Apache Mesos (including its frameworks Chronos and Marathon).

Therefore, this repository includes the following plugins:

* indigo_orchestrator.py: CLUES plugin to connect with the INDIGO orchestrator. Copy it to the ``cluesplugins`` directory of CLUES.
* condor.py: CLUES plugin to connect with the HTCondor.
* mesos.py:  CLUES plugin to connect with the Mesos, Chronos, and Marathon.


Quick testing
-------------------------
To test the elasticity capabilities we offer a prepared docker image.  
The docker container **grycap/jenkins:ubuntu14.04-clues-indigo-ec3** repository contains all the libraries and environment variables needed to test the plugins.  
This container uses [EC3](http://servproject.i3m.upv.es/ec3/) to deploy a cluster with clues integrated.  
To learn more about the EC3 usage you can check the [documentation](http://ec3.readthedocs.io/en/devel/).  

### Usage
To run the docker container:
```
docker run -it grycap/jenkins:ubuntu14.04-clues-indigo-ec3
```
then inside the container you can launch, for example, a mesos cluster:
```
./ec3 launch clues-test mesos docker ubuntu14-ramses -a auth.dat -u http://servproject.i3m.upv.es:8899
```
with this last command we are telling EC3 to launch cluster named **clues-test** that uses the **mesos** plugin and must have **docker** installed.  
The template used is specified in the file **ubuntu14-ramses** and the authorization file **auth.dat** must have the required users and passwords.

Info about the launch command, system templates, authorization files and more is available [here](http://ec3.readthedocs.io/en/devel/).

Once the cluster has been successfully deployed you can connect to it through the IP provided by EC3 or using (in our case):
```
./ec3 ssh clues-test

```
