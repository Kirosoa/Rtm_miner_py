import os
import sys
import threading
import socket
import urllib.parse
import json
import time
import struct
from binascii import hexlify, unhexlify
from hashlib import sha256
import random


class LogStyle():
    '''Increase terminal legibility'''
    
    # HELP: https://stackoverflow.com/questions/287871/how-to-print-colored-text-to-the-terminal
    NONE = ["[-]", '']
    LOG = ["[LOG]", "0;30;47"]
    WARNING = ["[WARNING]", "0;30;43"]
    ERROR = ["[ERROR]", "0;30;41"]
    OK = ["[OK]", "6;30;42"]
    

def debug(*messages):
    ''' for debug purpose only

        Even if called it doesn't print nothing if global variable DEBUG is set to False
    '''
    global DEBUG
    if DEBUG:
        for msg in messages:
            print("\x1b[0;34;1m"+f"{msg}"+"\x1b[0m")
    

def log(*messages, style=["[-]", ''], date=True):
    '''logging message with colored style

        style parameter should be set equal to some Variable of 'LogStyle' class
    '''
    log_str = style[0]
    log_style = style[1]
    print(f'\x1b[{log_style}m{log_str:^9}\x1b[0m', end='')
    
    if date:
        print('\x1b[1;30;1m - '+time.strftime("%d/%m/%y %H:%M:%S", time.gmtime())+" - \x1b[0m", end='') 
    
    log_space = f"\x1b[{log_style}m"+ " "*9 + "\x1b[0m"
    date_space = ' '*23 if date else ''
    
    print(("\n"+log_space+date_space).join([f"{msg}" for msg in messages]))


class JsonRcpClient(object):
    ''' Simple Json RCP client'''
    
    def __init__(self):
        self._socket = None
        self._rcp_thread = None
        self._message_id = 1
        self._lock = threading.RLock()
        self._requests = dict()

        self._url = None  # in case lost connection
    
    def rcp_thread_fun(self):
        data = ""
        
        while True:
            
            if '\n' in data:
                (line, data) = data.split('\n', 1)
            else:
                try:
                    chunk = self._socket.recv(1024)
                except ConnectionAbortedError:
                    log("Connection Lost", style=LogStyle.ERROR)
                    sys.exit() # TODO: reconnect and try again

                data += chunk.decode()
                continue
            
            reply = json.loads(line)
            # Find if the reply was a response from a specific request 
            # or a simple notification from the server (response = None)
            request = None
            
            if reply.get('id'):
                # get the reply id which refer to the corresponding response
                try:
                    request = self._requests[reply.get('id')] 
                except:
                    pass
            
            self._handle_reply(request, reply)
            
        
    def connect(self, url: str):
        """Create socket and start the receiving process

        Args:
            url (str): server of mining pool
        """
        self._url = url
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        parser = urllib.parse.urlparse(url)
        
        try:
            self._socket.connect((parser.hostname, parser.port))

            self._rcp_thread = threading.Thread(target=self.rcp_thread_fun)
            self._rcp_thread.daemon = True  # only for testing it should be not commented 
            self._rcp_thread.start()
        except Exception:
            log("Can't connect to server", style=LogStyle.WARNING)
            sys.exit()

    
    def send(self, method: str, params: list):
        """Send request to server

        Args:
            method (str): request method (ie. 'mining.subcribe', 'mining.authorize', ...)
            params (list): list of params required with the corresponding request method 
        """
        if not self._socket:
            log("No socket defined. First you need to connect to a server", style=LogStyle.WARNING)
            sys.exit()
            
        request = dict(id=self._message_id, method=method, params=params)
        self._requests[self._message_id] = request

        request = json.dumps(request)

        # print(request)
        with self._lock:
            # update message id that refer to a specific request
            self._message_id += 1
            self._socket.send((request+'\n').encode())

    def _handle_reply(self, request, reply):
        ''' override this function '''
        raise NotImplementedError("Override this function")


class Worker(object):
    
    def __init__(self, worker_name: str, finish_condition: threading.Condition, parent):
        self._workername = worker_name
        self._lock = threading.RLock()
        self._parent = parent # class: 'Miner'

        self._finish_condition = finish_condition # condition to notify Miner the job is finished
        self._worker_thread = None

        self._cleaned_flag = False  # used to clean all jobs
        self._stop_flag = False     # used to stop current jo
        self._found_share = False   # used to know whe
        self._current_job_id = None
        self._jobs_queue = dict()

        
        self._mine_thread = threading.Thread(target=self._work)
        self._mine_thread.daemon = True
        self._mine_thread.start()

    def clean_job(self):
        with self._lock:
            self._cleaned_flag =  True
            self._jobs_queue = dict()

    def _stop(self):
        with self._lock:
            self._stop_flag = True
    
    def remove_job(self, job_id):
        ''' remove job from worker jobs queue '''

        if job_id in self._jobs_queue:
            del self._jobs_queue[job_id]
        elif job_id == self._current_job_id:
            # if the job_id is the one currently processed stop it.
            self._stop_flag = True
        else:
            pass

    def stack_job(self, job_id, prev_hash, coinb1, coinb2, merkle_tree, 
                    version, nbits, ntime, extranonce1, extranonce2_size, target, start=0, stride=1):
        ''' ad job to worker queue '''
        new_job = dict(prev_hash=prev_hash,
                        coinb1=coinb1,
                        coinb2=coinb2,
                        merkle_tree=merkle_tree,
                        version=version,
                        nbits=nbits,
                        ntime=ntime,
                        extranonce1=extranonce1,
                        extranonce2_size=extranonce2_size,
                        target=target,
                        start=start, 
                        stride=stride)
        self._jobs_queue[job_id] = new_job

    def _work(self):
        
        while 1:
            
            if not len(self._jobs_queue) > 0:
                # if there is any work to do
                continue
            
            # reset flags
            self._cleaned_flag = False
            self._stop_flag = False

            # INIT
            self._current_job_id = next(iter(self._jobs_queue))  # take the next job in list
            job = self._jobs_queue.pop(self._current_job_id)
            log(f"{self._workername} started job {self._current_job_id}")

            # PROCESSING JOB
            for extranonce2 in range(2**(8*job['extranonce2_size'])-1):
                if self._cleaned_flag or self._stop_flag:
                    break

                extranonce2_b = self.calc_extranonce2_bin(extranonce2, job['extranonce2_size'])
                extranonce2_str = hexlify(extranonce2_b).decode('ascii')

                merkle_root_hex = self.calc_merkle_root_bin(extranonce2_str, job['extranonce1'], job['merkle_tree'], job['coinb1'], job['coinb2'])
                merkle_root_b = unhexlify(merkle_root_hex)

                header_prefix_b = self.to_little(job['version']) + \
                            self.swap_by_four(job['prev_hash']) + \
                            merkle_root_b + \
                            self.to_little(job['ntime']) + \
                            self.to_little(job['nbits'])
                
                for nonce in range(job['start'], 2**(4*8)-1, job['stride']):

                    if self._cleaned_flag or self._stop_flag:
                        break

                    nonce_b = struct.pack('<I', nonce)
                    hash = self.dbl_sha256(header_prefix_b+nonce_b)[::-1]

                    if hash <= job['target']:
                        log(f"Worker {self.workername} found nonce {hexlify(nonce_b)} for job id {self._current_job_id}")
                        self._stop_flag = True
            
                        with self._lock: # send result to miner for submitting
                            result = dict(type="result",
                                          workername=self._workername,
                                          job_id=self._current_job_id,
                                          extranonce2=hexlify(extranonce2_b).decode(),
                                          ntime=job['ntime'],
                                          nonce=hexlify(nonce_b[::-1]).decode())

                            self._parent.set_result(result) # write result to parent

                        with self._finish_condition:
                            self._finish_condition.notifyAll() # notify that job is done
    

    def calc_merkle_root_bin(self, extranonce2: str, extranonce1: str, merkle_tree: list, coinb1: str, coinb2: str):
        ''' given the extranonce2 return the merkleroot as bytearray'''
        coinbase = coinb1 + extranonce1 + extranonce2 + coinb2
        
        merkle_tree.insert(0, coinbase) # add coinbase to transaction list 
        merkle_root = self.merkle(merkle_tree)
        
        return merkle_root

    def merkle(self, hashList):
        ''' recursive function to calculate merkle root starting from a hash list '''
        if len(hashList) == 1:
            return hashList[0]
        newHashList = []
        # Process pairs. For odd length, the last is skipped
        for i in range(0, len(hashList)-1, 2):
            newHashList.append(self.hash2(hashList[i], hashList[i+1]))
        if len(hashList) % 2 == 1: # odd, hash last item twice
            newHashList.append(self.hash2(hashList[-1], hashList[-1]))
        return self.merkle(newHashList)

    @staticmethod
    def hash2(a, b):
        # Reverse inputs before and after hashing
        # due to big-endian / little-endian nonsense
        a1 = unhexlify(a)[::-1]
        b1 = unhexlify(b)[::-1]
        h = sha256(sha256(a1+b1).digest()).digest()
        return hexlify(h[::-1])

    @staticmethod
    def to_little(word):
        ''' return word to little endian format '''
        word = unhexlify(word)
        return word[::-1]

    @staticmethod
    def swap_by_four(word):
        ''' swap input every four byte and little endian '''
        word = unhexlify(word)
        
        if len(word)%8 != 0:
            log("Word length not divisible by 8", style=LogStyle.WARNING)
            sys.exit()
        else:
            return b''.join([word[4*i: 4*(i+1)][::-1] for i in range(int(len(word)/4))])

    @staticmethod
    def calc_extranonce2_bin(nonce, size):
        ''' format extranonce2 as requested from server '''
        if size == 8:
            return struct.pack("<Q", nonce)
        elif size == 4:
            return struct.pack("<I", nonce)
        else:
            return struct.pack("<H", nonce)

    @staticmethod
    def dbl_sha256(data: bytearray):
        ''' return double sha256 of the imput data '''
        return sha256(sha256(data).digest()).digest()

    def __str__(self):
        return f'WorkerName:{self._workername}'

class Miner(JsonRcpClient):
    ''' Miner Class to handle server and workers '''
    def __init__(self, username):
        super().__init__()
        self._username = username
        self._workers = []

        self._extranonce1 = None
        self._extranonce2_size = None
        self._target = None

        # use condition as notification when a worker find a share
        self._finish_condition = threading.Condition()
        # use this variable to set the result of the job done by the corresponding worker 
        self._worker_messages = []

        # this way we can handle multiple worker splitting the job
        self._worker_handler = threading.Thread(target=self._handle_workers)
        self._worker_handler.daemon = True
        self._worker_handler.start()


    def set_result(self, result):
        ''' used by a worker to return it's job to the parent Miner'''
        self._worker_messages.append(result)

    def _handle_workers(self):
        ''' handle of worker notification'''
        while 1:
            with self._finish_condition:
                self._finish_condition.wait()
                try:
                    msg = self._worker_messages.pop(0)
                    if msg['type'].lower() == 'result':

                        for worker in self._workers: # remove finished foj from other workers
                            worker.remove_job(msg['job_id'])

                        fullname = self._username + '.' + msg['workername']
                        result = [fullname, msg['job_id'], msg["estranonce2"], msg['ntime'], msg['nonce']] # format parameter for server

                        log("Submitting Share...")
                        self.send(method='mining.submit', params=result) # submit

                except:
                    pass
                   
    def _handle_reply(self, request, reply):
        debug(request, reply)

        if reply.get('error'): # minimum print error message 
            # TODO: handle specific code error
            log("An error occourred: ", reply.get('error'), style=LogStyle.ERROR)

        elif request:  # handle reply from a specific request
            if request.get('method') == 'mining.authorize':

                full_worker_name = request.get('params')[0]  # fullname = 'username.worker_name'
                _ , worker_name = full_worker_name.split('.') 

                if reply.get('result') == True: # add worker only if authorized
                    log(f"Authorized Worker: '{worker_name}'", style=LogStyle.OK)
                    # new_worker_obj = Worker(worker_name, self._finish_condition, self, random.randint(1, 3))
                    new_worker_obj = Worker(worker_name, self._finish_condition, parent=self) 
                    self._workers.append(new_worker_obj) # add worker
                    # debug(new_worker_obj)
                else:
                    log(f"Failed to authorize {full_worker_name}", style=LogStyle.ERROR) # something went wrong 

            if request.get('method') == 'mining.subscribe':
                # result be like:
                # [[["mining.set_difficulty", "subscription id 1"], ["mining.notify", "subscription id 2"]], "extranonce1", extranonce2_size]
                result = reply.get('result')
                self._extranonce1 = result[1]
                self._extranonce2_size = result[2]
            
            if request.get('method') == 'mining.submit':
                result = reply.get('result')
                if result:
                    log("Share accepted", style=LogStyle.OK)
                else:
                    LOG("Share not accepted", style=LogStyle.ERROR)
        else:
            # finally handle request from server without any request
            if reply.get('method') == 'mining.set_difficulty':
                self._difficulty = reply.get('params')[0]
                self._calc_target()
                log(f"Setted difficulty to {self._difficulty}", f"New Target: {hexlify(self._target).decode()}")

            if reply.get('method') == 'mining.notify':
                job_params = reply.get('params')
                log("Got new job", style=LogStyle.LOG)
                self.queue_new_job(*job_params)

    def _calc_target(self):
        ''' calculate target from difficulty given by pool'''

        # formula taken from https://en.bitcoin.it/wiki/Difficulty
        max_target = 0x00ffff*2**(8*(0x1d-3))

        target = int(max_target/self._difficulty)

        self._target = self._as64(target)

    def authorize_worker(self, worker_name, password):
        full_name = self._username + '.' + worker_name
        self.send(method='mining.authorize', params=[full_name, password])

    def subscrime_mining(self):
        # if len(self._workers) == 0:
        #     log("Authorize some worker oterwise you will get no reward", style=LogStyle.WARNING)
        self.send(method='mining.subscribe', params=[])

    def queue_new_job(self, *job_params):
        ''' stack received job to workers jobs queue '''
        job_id, prev_hash, coinb1, coinb2, merkle_tree, version, nbits, ntime, clean_job = job_params

        if len(merkle_tree) == 0:
            # sometime happened ??
            # maybe is not an error but who knows...
            return

        if clean_job:
            # clean job if necessary
            self.clean_workers_jobs()
            log("Cleaning Jobs")

        for worker_index, worker in enumerate(self._workers):
        
            worker.stack_job(job_id=job_id,
                    prev_hash=prev_hash,
                    coinb1=coinb1,
                    coinb2=coinb2,
                    merkle_tree=merkle_tree,
                    version=version,
                    nbits=nbits,
                    ntime=ntime,
                    extranonce1=self._extranonce1,
                    extranonce2_size=self._extranonce2_size,
                    target=self._target,
                    start=worker_index, 
                    stride=len(self._workers))

    def clean_workers_jobs(self):
        ''' notify all workers to stop the mining process '''
        for worker in self._workers:
            worker.clean_job()

    @staticmethod
    def _as64(integer):
        ''' return integer as 64 hex digit format '''
        return unhexlify(f'{integer:064x}')

if __name__ == "__main__":
    os.system('color')
    DEBUG = False
    
    miner = Miner("RGZxLiuzZau3NuZ4e3LzKcoxrkn4fC3SEG")
    miner.connect("stratum+tcp://pool.just4dns.co.uk:3008")
    miner.authorize_worker("Kiro", "x")

    # authorize multiple worker if you want
    # miner.authorize_worker("worker2", "pass")
    # miner.authorize_worker("worker3", "pass")
    
    miner.subscrime_mining()
    
    try:
        while 1:
            pass
    except KeyboardInterrupt:
        sys.exit()