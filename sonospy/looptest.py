from threading import Timer

class routine(object):
        t = {}
        def init(self):
                pass
        def run(self, s):
                self.t[s] = Timer(1.0, self.check, [s])
                self.t[s].start()
        def check(self, string):
                print string
                self.t[string] = Timer(1.0, self.check, [string])
                self.t[string].start()

def main():
        r = routine()
        r.run("crapcrapcrapcrapcrapcrapcrapcrapcrapcrapcrapcrap")

if __name__ == "__main__":
    main()

