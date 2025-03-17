#
# cleanup_fits.py -- removes old FITS files
#
# This script runs on the data analysis machines
#
# E. Jeschke
#
"""
Removes FITS files from a directory tree to bring the disk usage under
a certain percentage.  Skips files that do not end in '.fits'

Typical usage (assuming FITS directory is /data, and proper environment
vars are set):

# Shows you what it WOULD do:
$ ./cleanup_fits.py --loglevel=0 --stderr --fitsdir=/data --dry-run

# Actualy do it & log results
$ ./cleanup_fits.py --loglevel=0 --stderr --fitsdir=/data --action=delete --log=cleanup.log

# Continuously monitor filesystem and cleanup when disk usage rises
# above 80% and stop deleting when disk usage reaches 50%
$ ./cleanup_fits.py --loglevel=0 --fitsdir=/data --lo=50 --hi=80 \
    --action=delete --daemon --log=cleanup.log

TODO: make this into a common module for instruments.  They can import
it and run the daemon or cleanup functions as tasks.
"""
import sys, re, time
import os, fnmatch
import logging

from g2base import ssdlog, Bunch
from g2base.astro.frame import getFrameInfoFromPath

# minimum number of days a file needs to be around before it is
# considered for expiration
keep_threshold_days = 7
keep_threshold_age = 60 * 60 * 24 * keep_threshold_days


def get_disk_usage(path):
    """Takes a path to a directory and returns the percentage of space
    used on that filesystem (as a float).
    """

    res = os.statvfs(path)

    #scale = (res.f_bsize / 1024)

    # FS size in native fs size blocks
    fs_size = res.f_blocks #* scale
    fs_avail = res.f_bavail #* scale

    # This is not quite accurate wrt "df", but close enough
    pctused = 1.0 - (float(fs_avail) / float(fs_size))

    return pctused

def recursive_glob(treeroot, pattern):
  results = []
  for base, dirs, files in os.walk(treeroot):
    goodfiles = fnmatch.filter(files, pattern)
    results.extend(os.path.join(base, f) for f in goodfiles)
  return results


def cleanup(options, args, logger):
    """Runs a cleanup on the directory specified in options.fitsdir.
    Stops when disk usage drops below the low water mark threshold
    specified by options.lowater
    """

    files = recursive_glob(options.fitsdir, "*.fits")

    # First pass.  Record information about files in FITS dir.
    logger.info("Cleanup PASS 1: information gathering.")
    fitslist = []
    cur_time = time.time()

    for fitspath in files:

        logger.debug("Examining file '%s'" % fitspath)

        # If this is not a .fits file then move on
        (pfx, ext) = os.path.splitext(fitspath)
        if not re.match(r'^\.fits$', ext, re.IGNORECASE):
            logger.info("No FITS extension: '%s'" % fitspath)
            continue

        # Assume: no age
        age = 0

        # Record modification time of file
        try:
            stat = os.stat(fitspath)
            age = stat.st_mtime

        except OSError as e:
            logger.error("Error stat(%s): %s" % (fitspath, str(e)))
            continue

        # Skip files that don't look like Subaru frames
        try:
            res = getFrameInfoFromPath(fitspath)

        except Exception as e:
            logger.info("Not a Subaru FITS frame: '%s': %s" % (
                fitspath, str(e)))
            continue

        # Skip files that are younger than the minimum required age
        delta = cur_time - age
        if not (delta > keep_threshold_age):
            filedate = time.strftime("%Y-%m-%d %H:%M:%S",
                                     time.localtime(age))
            logger.info("Skipping too young file: (%s) '%s'" % (
                filedate, fitspath))
            continue

        bnch = Bunch.Bunch(fitspath=fitspath, age=age)
        fitslist.append(bnch)

    # Sort by age
    fitslist.sort(key=lambda x: x.age)
    #print(fitslist)

    delete(options, logger, fitslist)


def delete(options, logger, files):
    # Second pass.  Remove files.  Stop deleting when the free space reaches
    # a certain threshold.
    logger.info("Cleanup PASS 2: file deletion.")
    for bnch in files:

        # Check if we should stop because we have fallen below the low
        # water mark
        if options.lowater:
            pctused = get_disk_usage(options.fitsdir)
            if pctused < (float(options.lowater) / 100.0):
                logger.info("Filesystem usage has dropped below %3d%%" % (
                    options.lowater))
                logger.info("Stopping further deletion.")
                break

        fitspath = bnch.fitspath
        filedate = time.strftime("%Y-%m-%d %H:%M:%S",
                                 time.localtime(bnch.age))

        logger.info("Deleting '%s' aged %s" % (fitspath, filedate))
        try:
            if not options.dry_run:
                os.remove(fitspath)

        except OSError as e:
            logger.error("Error deleting '%s': %s" % (fitspath, str(e)))

    logger.info("Pass 2 finished.")

    pctused = get_disk_usage(options.fitsdir)
    if pctused > (float(options.lowater) / 100.0):
        logger.warn("Filesystem could not be brought below %3d%%!" % (
            options.lowater))

def check_usage(options, args, logger):
    # Check if we should delete because we have risen above the high
    # water mark
    pctused = get_disk_usage(options.fitsdir)
    logger.debug("Disk usage is %3.2f%%" % (pctused * 100))
    if pctused > (float(options.hiwater) / 100.0):
        logger.info("Filesystem usage has risen above %3d%%" % (
                        options.hiwater))
        logger.info("Invoking cleanup.")
        cleanup(options, args, logger)
    else:
        logger.info("Filesystem usage (%3d%%) is below %3d%% threshold" % (
                        int(pctused*100), options.hiwater))


def main(options, args):

    logname = 'cleanup_fits'
    logger = ssdlog.make_logger(logname, options)

    try:
        if options.daemon:
            while True:
                check_usage(options, args, logger)

                logger.debug("Sleeping for %3.2f secs" % options.interval)
                time.sleep(options.interval)
        else:
            check_usage(options, args, logger)

    except KeyboardInterrupt:
        logger.error("Caught keyboard interrupt!")

    logger.info("Cleanup terminating.")


# END
