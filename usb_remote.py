"""USB GUI RPC for the pinned ESP32 port; no arbitrary RPC or CLI passthrough.
Wire tags come from components/flipper_protobuf/{flipper,gui}.pb.h.
"""
import atexit
import base64
import os
import threading
import time
from mcp.server.fastmcp.exceptions import ToolError


def varint(n):
    out=bytearray()
    while n>127: out.append((n&127)|128); n>>=7
    out.append(n)
    return bytes(out)


def number(tag,n): return varint(tag<<3)+varint(n)
def blob(tag,data): return varint((tag<<3)|2)+varint(len(data))+data


def read_varint(data,pos=0):
    value=0
    for shift in range(0,35,7):
        if pos>=len(data): raise EOFError()
        b=data[pos];pos+=1;value|=(b&127)<<shift
        if not b&128:return value,pos
    raise ValueError('invalid varint')


def fields(data):
    result={};pos=0
    while pos<len(data):
        key,pos=read_varint(data,pos);tag=key>>3;wire=key&7
        if not tag:raise ValueError('invalid tag')
        if wire==0:value,pos=read_varint(data,pos)
        elif wire==2:
            size,pos=read_varint(data,pos)
            if size>65536 or pos+size>len(data):raise ValueError('invalid size')
            value=data[pos:pos+size];pos+=size
        elif wire in (1,5):
            size=8 if wire==1 else 4
            if pos+size>len(data):raise ValueError('truncated scalar')
            value=data[pos:pos+size];pos+=size
        else:raise ValueError('unsupported wire type')
        result[tag]=value
    return result


class UsbRemote:
    def __init__(self):
        self.path=os.environ.get('TEMBED_SERIAL','')
        self.serial=None;self.thread=None;self.stop=threading.Event()
        self.control=threading.RLock();self.lock=threading.Lock()
        self.pending={};self.counter=0;self.frame=None;self.error='';self.connected=False
        atexit.register(self.close)

    def snapshot(self):
        with self.lock:
            return {'configured':bool(self.path),'connected':self.connected,'error':self.error,'frame':self.frame}

    def connect(self):
        with self.control:
            if self.connected:return self.snapshot()
            self.close()
            if not self.path:raise ToolError('USB not configured: set TEMBED_SERIAL and map the device')
            try:
                import serial
                port=serial.Serial(port=None,baudrate=115200,timeout=.2,write_timeout=2,exclusive=True)
                port.port=self.path;port.dtr=False;port.rts=False;port.open()
                self.serial=port
                port.reset_input_buffer();port.dtr=True
                port.write(b'\r');port.flush()
                received=bytearray();deadline=time.monotonic()+3
                while b'>: ' not in received and time.monotonic()<deadline:
                    received.extend(port.read(256))
                    if len(received)>4096:raise ValueError('unexpected USB console')
                if b'>: ' not in received:raise ValueError('qFlipper prompt missing; enable qFlipper on the device')
                port.write(b'start_rpc_session\r');port.flush()
                received=bytearray();deadline=time.monotonic()+3
                marker=b'start_rpc_session\r\n'
                while marker not in received and time.monotonic()<deadline:
                    received.extend(port.read(256))
                    if len(received)>4096:raise ValueError('invalid handshake')
                if marker not in received:raise ValueError('RPC handshake not acknowledged')
                tail=bytes(received).split(marker,1)[1]
                self.stop.clear()
                with self.lock:self.error='';self.frame=None;self.connected=True
                self.thread=threading.Thread(target=self._read,args=(tail,),daemon=True)
                self.thread.start()
                self._command(20,b'')
                return self.snapshot()
            except Exception as exc:
                self.close()
                with self.lock:self.error=str(exc)
                raise ToolError('USB connection failed: '+str(exc)) from exc

    def _read(self,initial):
        buffer=bytearray(initial)
        try:
            while not self.stop.is_set():
                chunk=self.serial.read(4096)
                buffer.extend(chunk)
                if len(buffer)>131072:raise ValueError('USB buffer limit')
                while buffer:
                    try:size,start=read_varint(buffer)
                    except EOFError:break
                    if size>65536:raise ValueError('RPC message too large')
                    if len(buffer)<start+size:break
                    msg=fields(bytes(buffer[start:start+size]));del buffer[:start+size]
                    if 22 in msg:
                        frame=fields(msg[22]);raw=frame.get(1,b'');orientation=frame.get(2,0)
                        if len(raw)!=1024 or orientation not in (0,1,2,3):raise ValueError('unsupported screen format')
                        with self.lock:self.frame={'data':base64.b64encode(raw).decode(),'orientation':orientation,'width':128,'height':64,'received_at':time.time()}
                    cid=msg.get(1,0)
                    with self.lock:
                        pending=self.pending.get(cid)
                        if pending:
                            pending['status']=msg.get(2,0);pending['event'].set()
        except Exception as exc:
            if not self.stop.is_set():
                with self.lock:self.error=str(exc)
        finally:
            with self.lock:
                self.connected=False
                for p in self.pending.values():p['event'].set()

    def _command(self,tag,payload):
        if not self.connected:raise ToolError('USB disconnected; reconnect explicitly')
        self.counter=(self.counter%0xfffffffe)+1;cid=self.counter
        pending={'event':threading.Event(),'status':None}
        with self.lock:self.pending[cid]=pending
        try:
            message=number(1,cid)+blob(tag,payload)
            self.serial.write(varint(len(message))+message);self.serial.flush()
            if not pending['event'].wait(3):raise ToolError('USB RPC timeout; command is not retried')
            if pending['status']!=0:raise ToolError('USB RPC failed: '+str(pending['status']))
        finally:
            with self.lock:self.pending.pop(cid,None)

    def key(self,key,long=False):
        keys={'up':0,'down':1,'right':2,'left':3,'ok':4,'back':5}
        if key not in keys or type(long) is not bool:raise ToolError('Invalid button')
        with self.control:
            try:
                self._command(23,number(1,keys[key])+number(2,0))
                try:self._command(23,number(1,keys[key])+number(2,3 if long else 2))
                finally:self._command(23,number(1,keys[key])+number(2,1))
                return {'ok':True}
            except Exception as exc:
                self.close()
                raise ToolError('Button sequence interrupted; check device before repeating: '+str(exc)) from exc

    def close(self):
        with self.control:
            self.stop.set()
            if self.thread and self.thread is not threading.current_thread():self.thread.join(timeout=1)
            if self.serial:
                try:self.serial.close()
                except Exception:pass
            self.serial=None;self.thread=None
            with self.lock:self.connected=False;self.frame=None
            return {'connected':False}
