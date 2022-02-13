# Cryptominer-python

simple mining script to mine bitcoin using stratum(v1) protocol

## Table of contents
- [General Info](#general-info)
- [Usage](#sample-usage)
- [Inspiration](#inspiration)
- [License](#license)
## General Info
This code was tested using slushpool but any other pool which use stratum protocol should work. This repo was developed to work with bitcoin but other cryptovalues with sha256 proof-of-work should work. This project is only for fun and to understand how mining work. Infact the process use CPU to mine that is worthless because it take ages to mine something XD.

## Sample Usage
First step is to define a miner which inherit from *Miner* class using the username subscribed to the pool
```python
miner = Miner("username")
```
Then connect to the pool stratum server

```python
# i.e. for slushpool server
miner.connect("stratum+tcp://stratum.slushpool.com:3333") 
```

Next step is to authorize workers. Multiple workers can be authorized. first parameter is *workername* meanwhile the second parameter is *password*
```python
miner.authorize_worker("worker1", "pass")
# miner.authorize_worker("worker2", "pass")
# miner.authorize_worker("worker3", "pass")
```
Finally start mining subscribing to the mining service
```python
miner.subscrime_mining()
```
## Inspiration
This miner is based by a repo of @ricmoo [nightminer](https://github.com/ricmoo/nightminer). Code was written for python 2.7.x. My version revisited ricoo's code adding some feature like workers have queue for Job. I've only implemented proof-of-work for bitcoin mining because i've tested it on slushpool.com. This repo is a start point to develop another project i have in mind: using fpga like *altera de0-nano* with a rasperry pi to handle server comunication.

## License
cryptominer-python use GNU license. See [LICENSE](https://github.com/DavideRuzza/cryptominer-python/blob/main/LICENSE)
