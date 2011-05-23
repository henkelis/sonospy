                        import traceback        
                        traceback.print_stack()
                        print self.__dict__
                        def classtree(cls, indent):
                            print '.'*indent, cls.__name__        # print class name here
                            for supercls in cls.__bases__:        # recur to all superclasses
                                classtree(supercls, indent+3)     # may visit super > once
                        classtree(self.__class__, 3)

