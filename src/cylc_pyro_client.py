#!/usr/bin/env python

import os, sys
import socket
import Pyro.core, Pyro.errors
from optparse import OptionParser
from time import sleep
from passphrase import passphrase, PassphraseNotFoundError, SecurityError
from port_scan import get_port, check_port

class client( object ):
    def __init__( self, suite, owner=os.environ['USER'], host=socket.getfqdn(), port=None ):
        self.suite = suite
        self.owner = owner
        self.host = host
        self.port = port

        self.passphrase = None
        try:
            self.passphrase = passphrase( suite ).get()
        except PassphraseNotFoundError:
            # assume this means the suite requires no passphrase
            pass
        except SecurityError,x:
            print "WARNING: There is a problem with the secure passphrase for suite " + suite + ":"
            print x
            print "Continuing, but access will be denied if the suite requires a passphrase."

    def get_proxy( self, target ):
        # callers need to check for port_scan.SuiteIdentificationError:
        if self.port:
            check_port( self.suite, self.port, self.owner, self.host )
        else:
            self.port = get_port( self.suite, self.owner, self.host, pphrase=self.passphrase )

        # get a pyro proxy for the target object
        objname = self.owner + '.' + self.suite + '.' + target

        uri = 'PYROLOC://' + self.host + ':' + str(self.port) + '/' + objname 
        # callers need to check for Pyro.NamingError if target object not found:
        proxy = Pyro.core.getProxyForURI(uri)

        # set set passphrase if necessary:
        if self.passphrase:
            proxy._setIdentification( self.passphrase )

        return proxy
