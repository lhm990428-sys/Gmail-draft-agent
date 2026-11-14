import os


class RuntimeOwnership:
    def __init__(self,directory):
        directory.mkdir(parents=True,exist_ok=True)
        self.handle=(directory/"runtime.lock").open("a+b")
        self.handle.seek(0,2)
        if self.handle.tell()==0:self.handle.write(b"1");self.handle.flush()
        self.handle.seek(0)
        try:
            if os.name=="nt":
                import msvcrt
                msvcrt.locking(self.handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self.handle.close()
            raise RuntimeError("ANOTHER_RUNTIME_OWNS_THIS_DATABASE") from None
    def close(self):
        if self.handle.closed:return
        self.handle.seek(0)
        if os.name=="nt":
            import msvcrt
            msvcrt.locking(self.handle.fileno(),msvcrt.LK_UNLCK,1)
        self.handle.close()
