#!/usr/bin/env python
from string import split
from time import sleep
from sys import argv, exit
from re import sub
from sourceforge import getProjectSpec
from database import Doap
from datetime import datetime

from apt_pkg import ParseTagFile

import tempfile, os

## DOAP is inside our current Launchpad production DB
DOAPDB = "launchpad_dev"

## USE ONLY ONE MODE !!!!!!!!!!!!!!
## Update mode
UPDATE = True

## Insert mode
INSERT = False
package_root = "/ubuntu/"
distrorelease = "hoary"
component = "main"


## Web search interval avoiding to be blocked by high threshould
## of requests reached by second
SLEEP = 20

## Entries not found
LIST = 'nicole_notfound'

sf = 0
fm = 0
both = 0
skip = 0

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

def get_current_packages():
    packagenames = []

    print '@ Retrieve SourcePackage Information From Soyuz'

    index = 0
    
    ## Get SourceNames from Sources file (MAIN)
    sources_zipped = os.path.join(package_root, "dists", distrorelease,
                                  component, "source", "Sources.gz")
    srcfd, sources_tagfile = tempfile.mkstemp()
    os.system("gzip -dc %s > %s" % (sources_zipped,
                                    sources_tagfile)) 
    sources = ParseTagFile(os.fdopen(srcfd))
    while sources.Step():        
        packagenames.append(sources.Section['Package'])
        index += 1

    print '@ %d SourcePackages from Soyuz' % index        
    return index, packagenames


def grab_web_info(name):
    print '@ Looking for %s on Sourceforge' % name    
    try:
        data_sf = getProjectSpec(name)
        print '@\tFound at Sourceforge'        
    except:
        print '@\tNot Found'
        data_sf = None

    print '@ Looking for %s on FreshMeat' % name        
    try:
        data_fm = getProjectSpec(name, 'fm')
        print '@\tFound at FreshMeat'
    except:
        print '@\tNot Found'
        data_fm = None
            
    return data_sf, data_fm

def grab_for_product(data, project, name):
    if project == name:
        doap.ensureProduct(project, data, name)
        print '@\tCreating a Default Product'
        return

    data_sf, data_fm = grab_web_info(name)        

    if data_sf:
        doap.ensureProduct(project, data_sf, name)
        print '@\tCreating Sourceforge Product'        
    elif data_fm:
        doap.ensureProduct(project, data_fm, name)
        print '@\tCreating a FreshMeat Product'
    else:
        print '@\tNo Product Found for %s' % name

def name_filter(package):
    ## split the package name by '-' and use just the first part
    name = split(package, '-')[0]        
    
    ## XXX (project+valid_name) cprov 20041013
    ## for god sake !!! we should avoid names shorter than 3 (!!)
    ## chars 
    if len(name) < 3:
        name = package.replace('-', '')
        
    print '@ Proposed Project name %s'% name

    return name

def updater(doap, product_name):
    global fm, sf, both

    data_sf, data_fm = grab_web_info(product_name)

    if data_sf and not data_fm:
        ##present_data(data_sf)            
        sf +=1            
        doap.updateProduct(data_sf, product_name)
    elif data_fm and not data_sf:
        ##present_data(data_fm)
        fm += 1
        doap.updateProduct(data_fm, product_name)
    elif data_sf and data_fm:
        ##present_data(data_sf)
        ##present_data(data_fm)
        both += 1
        ## Do we really preffer sourceforge ???
        doap.updateProduct(data_sf, product_name)
    else:
        print '@\tNo Product Found for %s' % product_name
        append_list(product_name)                

def inserter(doap, product_name):
    global fm, sf, both

    data_sf, data_fm = grab_web_info(product_name)

    if data_sf and not data_fm:
        ##present_data(data_sf)            
        sf +=1            
        doap.ensureProduct(None, data_sf,None)
    elif data_fm and not data_sf:
        ##present_data(data_fm)
        fm += 1
        doap.ensureProduct(None, data_fm, None)
    elif data_sf and data_fm:
        ##present_data(data_sf)
        ##present_data(data_fm)
        both += 1
        ## Do we really preffer sourceforge ???
        doap.ensureProduct(None, data_sf, None)
    else:
        print '@\tNo Product Found for %s' % product_name
        append_list(product_name)                

    
def grabber(package, name):
    ##for god sake again ...
    global fm, sf, both
    
    data_sf, data_fm = grab_web_info(name)        
            
    if data_sf and not data_fm:
        ##present_data(data_sf)            
        sf +=1            
        doap.ensureProject(data_sf)
        ## Partially Commit DB Project Info
        doap.commit()
        grab_for_product(data_sf, name, package)
        
    elif data_fm and not data_sf:
        ##present_data(data_fm)
        fm += 1
        doap.ensureProject(data_fm)
        ## Partially Commit DB Project Info
        doap.commit()
        grab_for_product(data_fm, name, package)
        
    elif data_sf and data_fm:
        ##present_data(data_sf)
        ##present_data(data_fm)
        both += 1
        doap.ensureProject(data_sf)
        ## Partially Commit DB Project Info
        doap.commit()
        grab_for_product(data_fm, name, package)    
        
    else:
        print '@\tNo Product Found for %s' % name
        append_list(package)                
        

def present_data(data):
    print '========================================================'
    for item in data.keys():
        print item + ':', data[item] 
    print '========================================================'


if __name__ == "__main__":
    # get the DB abstractors
    doap = Doap(DOAPDB)

    if len(argv) > 1:
        mode = argv[1][1:]
    else:
        mode = 'h'

    print '\t\tWelcome to Nicole'
    print 'An Open Source Project Information Finder'
        
    index = 0
    clean_list()
    
    if mode == 'o':
        print 'Running OLD mode'
        tries, packages = get_current_packages()
    
        for package in packages:
            index += 1
            print ' '
            print '@ Grabbing Information About the %s (%d/%d)'% (package,
                                                                  index,
                                                                  tries)
            name = name_filter(package)
            
            if not doap.getProject(name):
                
                ## Grab data 
                grabber(package, name)            
                ## Partially Commit DB Product Info
                doap.commit()            
                ##It should prevent me to be blocked again by SF
                sleep(SLEEP)
            else:
                print '@\tSkipping it, Already included'
                skip += 1

    elif mode == 'i':
        print 'Running INSERT mode'        
        if len(argv) < 3:
            exit("Not enough Arguments")
        else:
            f = open(argv[2], 'r')
            products = f.read().strip().split('\n')
            print products
            tries = len(products)
 
        for product in products:
            index += 1
            print ' '
            print '@ Grabbing Information About the %s (%d/%d)'% (product,
                                                                  index,
                                                                  tries)
            updater(doap, product)
            ## Partially Commit DB Product Info
            doap.commit()            
            ##It should prevent me to be blocked again by SF
            sleep(SLEEP)
           
                
    elif mode == 'u':
        print 'Running UPDATE mode'        
        tries, products = doap.getProductsForUpdate()
        
        for product in products:
            index += 1
            print ' '
            print '@ Grabbing Information About the %s (%d/%d)'% (product[3],
                                                                  index,
                                                                  tries)
            updater(doap, product[3])
            ## Partially Commit DB Product Info
            doap.commit()            
            ##It should prevent me to be blocked again by SF
            sleep(SLEEP)

    elif mode == 'h':
        print 'Usage:'
        print 'nicole.py -o         OLD MODE, Fill DOAP from'
        print '                     Package Archive'
        print 'nicole.py -i <file>  INSERT MODE, insert products'
        print '                     from a file list'
        print 'nicole.py -u         UPDATE MODE, update products'
        print '                     with autoupdate AND reviewed == True'
        exit("See the Usage")

        
    fail = tries - (sf + fm + both + skip)

    doap.close()

    print '@\t\tSourceforge (only) %d' % sf
    print '@\t\tFreshMeat (only)   %d' % fm
    print '@\t\tBoth               %d' % both
    print '@\t\tFailures           %d' % fail
    print '@\t\tSkips:             %d' % skip
    print '@\t\tTries:             %d' % tries
    print '@ Thanks for using Nicole'
