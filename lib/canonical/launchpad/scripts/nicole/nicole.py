#!/usr/bin/env python
from string import split
from time import sleep
from sys import argv, exit
from re import sub
from datetime import datetime

#local imports
from database import Doap

#Morgan's import
import sourceforge 


## DOAP is inside our current Launchpad production DB
DOAPDB = "launchpad_dev"


## Web search interval avoiding to be blocked by high threshould
## of requests reached by second
SLEEP = 10

## Entries not found
LIST = 'nicole_notfound'


def clean_list():
    print """Cleaning 'Not Found' File List"""
    f = open(LIST, 'w')
    timestamp = datetime.isoformat(datetime.utcnow())
    f.write('Generated by Nicole at UTC %s\n' % timestamp)
    f.close()

def append_list(data):
    print """@\tAppending %s in 'Not Found' File List""" % data
    f = open(LIST, 'a')
    f.write('%s\n' % data)
    f.close()


def merge_data(pref, sup):
    ##iter through the suplementar keys 
    for key in sup.keys():
        ## if there is something new, add new key
        if key not in pref.keys():
            pref[key] = sup[key]
        ## if the preffered value is None 
        elif sup[key] and not pref[key] :
            pref[key] = sup[key]
        ## Otherwise keep the preffered
        else:
            pass

    return pref

def grab_web_info(name):
    datas = {}

#     repositories = (('sf', 'Sourceforge'),
#                     ('fm', 'Freshmeat'))

    repositories = (('fm', 'Freshmeat'),)

    for short, desc in repositories:

        print '@ Looking for %s on %s' % (name, desc)
        try:
            data = sourceforge.getProductSpec(name, short)
            print '@\tFound at %s' % desc        
        except sourceforge.Error:
            data = {}
            print '@\tNot Found'
        datas[short] = data

    return datas['fm']
#    return merge_data(datas['fm'], datas['sf'])

def createorupdate(doap, product_name):
    data = grab_web_info(product_name)

    if data:
        doap.ensureProduct(data, product_name, None)
    else:
        print '@\tNo Product Found for %s' % product_name
        append_list(product_name)                


if __name__ == "__main__":
    # get the DB abstractors
    doap = Doap(DOAPDB)

    print '\tNicole: Product Information Finder'

    index = 0
    clean_list()
    
    if len(argv) > 1:
        f = open(argv[1], 'r')
        products = f.read().strip().split('\n')
        #print products
        tries = len(products)
    else:
        tries, products = doap.getProductsForUpdate()
        #print products

    for product in products:
        index +=1
        print ' '
        print '@ Search for "%s" (%d/%d)' % (product,
                                             index,
                                             tries)
        createorupdate(doap, product)
        ## Partially Commit DB Product Info
        doap.commit()            
        ## We sleep to avoid overloading SF or FM servers
        sleep(SLEEP)
 
    doap.close()
    print 'Thanks for using Nicole'
