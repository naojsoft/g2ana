#
# T. Inagaki
# E. Jeschke
#

import sys
import os
import re
import signal
import shlex
import subprocess
import getpass

from ginga import toolkit
toolkit.use('qt5')
from ginga.gw import Widgets

from g2base import ssdlog, Bunch
from g2base.remoteObjects import remoteObjects as ro

from g2ana.icons import __file__
icondir, _nm = os.path.split(__file__)


class ANAError(Exception):
    """Base class for exceptions in this module."""
    pass

class Process(object):

    def __init__(self, logger):

        self.logger = logger
        self.processes = []

    def execute(self, args):

        self.logger.debug('executing %s' %args)
        try:
            process = subprocess.Popen(args)
        except Exception as e:
            res = '%s' %str(e)
            self.logger.error('error: execution. %s' %res)
        else:
            if process.pid:
                self.processes.append(process)
            res = 0
        finally:
            return res

    def terminate(self):

        for process in self.processes:
            try:
                self.logger.debug('terminating pid=%d' %process.pid)
                process.terminate()
            except Exception as e:
                self.logger.error('error: terminating process. %s' %e)


class AnaMenu(object):

    def __init__(self, root, logger, svcname, rohost, port, monport, hostname):

        # holds widgets of interest
        self.w = Bunch.Bunch()
        self.w.root = root

        self.logger = logger
        self.process = Process(logger)
        self.hostname = hostname
        self.svcname = svcname
        self.rohost = rohost
        self.fitsviewer_port = port
        self.fitsviewer_monport = monport
        self.propid = None
        self.propfile = None
        self.logger = logger
        self.__init_propid_entry()
        #self.__set_propfile()
        self.title_suffix = "\u3041\u306A \u3081\u306C"  # あな めぬ

        self.action_list = [
            ('COMICS', self.launch_comics),
            ('FOCAS', self.launch_focas),
            ('IRCS', self.launch_ircs),
            ('HDS', self.launch_hds),
            ('MOIRCS', self.launch_moircs),
            ]

    def setup_ui(self):

        self.logger.debug("setting up ana menu gui")
        vbox = Widgets.VBox()

        menubar = Widgets.Menubar()
        menu = menubar.add_name('File')
        menu.add_separator()
        item = menu.add_name('Quit')
        item.add_callback('activated', lambda w: self.quit())
        vbox.add_widget(menubar, stretch=0)

        lbl = Widgets.Label(self.svcname + " " + self.title_suffix)
        lbl.set_font('sans', 24)
        vbox.add_widget(lbl, stretch=0)
        self.w.title = lbl

        tb0 = Widgets.Toolbar(orientation='horizontal')
        fr = Widgets.Frame('PropID:')
        fr.set_widget(tb0)
        entry = Widgets.TextEntry()
        self.w.propid = entry
        tb0.add_widget(entry)
        a = tb0.add_action('Set')
        a.add_callback('activated', self.set_propid)
        vbox.add_widget(fr)

        # buttons for Gen2 application
        tb1 = Widgets.Toolbar(orientation='horizontal')
        fr = Widgets.Frame('Viewers:')
        fr.set_widget(tb1)
        vbox.add_widget(fr)

        tb2 = Widgets.Toolbar(orientation='horizontal')
        fr = Widgets.Frame('Instrument:')
        fr.set_widget(tb2)
        vbox.add_widget(fr)

        tb3 = Widgets.Toolbar(orientation='horizontal')
        fr = Widgets.Frame('Etc:')
        fr.set_widget(tb3)
        vbox.add_widget(fr)

        status = Widgets.StatusBar()
        vbox.add_widget(status)
        self.w.msgbar = status

        # Add some buttons to the tool bars.
        a = tb1.add_action('Ginga', toggle=False,
                           iconpath=os.path.join(icondir, 'view-file.png'),
                           iconsize=(24, 24))
        a.add_callback('activated', lambda w: self.launch_fits_viewer())
        a.set_tooltip("Start Gen2 FITS viewer")
        a = tb1.add_action('Ds9', toggle=False,
                           iconpath=os.path.join(icondir, 'view-file.png'),
                           iconsize=(24, 24))
        a.add_callback('activated', lambda w: self.launch_ds9())
        a.set_tooltip("Start ds9 FITS viewer")
        a = tb1.add_action('Skycat', toggle=False,
                           iconpath=os.path.join(icondir, 'view-file.png'),
                           iconsize=(24, 24))
        a.add_callback('activated', lambda w: self.launch_skycat())
        a.set_tooltip("Start skycat FITS viewer")

        for name, action in self.action_list:
            a = tb2.add_action(name, toggle=False,
                               iconpath=os.path.join(icondir, 'camera.png'),
                               iconsize=(24, 24))
            def launch_inst(w):
                action()
            a.add_callback('activated', launch_inst)
            a.set_tooltip("Start data analysis package for %s" % (name))

        a = tb3.add_action('Terminal', toggle=False,
                           iconpath=os.path.join(icondir, 'terminal.png'),
                           iconsize=(24, 24))
        a.add_callback('activated', lambda w: self.launch_terminal())
        a.set_tooltip("Start a terminal on analysis server")
        a = tb3.add_action('StatMon', toggle=False,
                           iconpath=os.path.join(icondir, 'statmon.png'),
                           iconsize=(28, 24))
        a.add_callback('activated', lambda w: self.launch_statmon())
        a.set_tooltip("Start Gen2 status monitor")

        self.w.root.set_widget(vbox)

        self.logger.debug("ana menu gui done")

    def __set_propfile(self):

        filename = 'propid'
        try:
            homedir = os.environ['HOME']
        except Exception:
            homedir = '/home/%s' % getpass.getuser()
        finally:
            self.propfile = os.path.join(homedir, filename)
            self.logger.debug('propfile=%s' %self.propfile)


    def expand_log(self, expander):

        if expander.get_expanded():
            expander.remove(expander.child)
            self.window.resize(self.window_width, self.window_height)
        else:
            expander.add(self.sw_expander)            #expander.add(self.textview_log)

#            iter=self.buffer_log.get_start_iter()
#            self.buffer_log.insert(iter, 'test... %d\n' %self.c)
#            self.c+=1

    def __init_propid_entry(self):
        self.get_propid()

        if self.propid:
            #self.__set_propfile()
            #self.write_propid()
            self.w.propid.set_text(self.propid)

    def get_propid(self):
        oid = getpass.getuser()
        self.logger.debug('user=%s' %oid)
        # for now, handle both u and o account. note: eventually, o-account only
        m = re.search(r'(?<=u|o)\d{5}', oid)
        if m:
            self.propid = 'o%s' %m.group(0)
            self.logger.debug('propid<%s>' %self.propid)

    def quit(self):
        self.logger.debug('quitting.')
        # self.remove_propid() # multiple users launch/quit anamenu w/o opening fitsviewer
        self.process.terminate()

        root, self.w.root = self.w.root, None
        root.delete()

    def is_propid(self, propid):
        try:
            m = re.search(r'(?<=o)\d{5}', propid)
        except Exception:
            m = None
        return m

    def set_propid(self, w):
        propid = self.w.propid.get_text().strip()
        res = self.is_propid(propid)
        if res:
            self.propid = propid
            self.__set_propfile()
            self.write_propid()
        else:
            self.w.msgbar.set_message("Bad propid: '%s'" % (propid))
            w.set_text(self.propid)

    def __execute(self, cmd, procname):
        ''' execute applications '''
        ## iter = self.buffer_log.get_start_iter()

        error = self.process.execute(cmd)

        ## if not error:
        ##     self.buffer_log.insert(iter, '%s started...\n' %(procname))
        ## else:
        ##     self.logger.error('error: launching %s.. %s'  %(procname, error))
        ##     self.buffer_log.insert(iter, 'error: %s. %s\n' %(procname, error))

    def remove_propid(self):
        try:
            os.remove(self.propfile)
        except Exception as e:
            self.logger.error('error: removing propfile. %s' %str(e))

    def write_propid(self):
        try:
            with open(self.propfile, 'w') as f:
                f.write(self.propid)
            #os.chmod(self.propfile, 0o666)
        except Exception as e:
            self.logger.error('error: writing propid. %s' %str(e))

    def get_gen2home(self):
        try:
            gen2home = os.environ['GEN2HOME']
        except OSError:
            gen2home = '/home/gen2/Git/python/Gen2'
        finally:
            return gen2home

    @property
    def loghome(self):
        return os.path.join('/home', self.propid)

    def launch_fits_viewer(self):
        ''' fits viewer '''

        #fitshome = '/home/gen2/Git/Fitsview'
        fitshome = os.path.join(self.get_gen2home(), 'fitsview')

        command_line = "{0}/fitsview.py --rohosts={1} --modules=ANA --plugins=Ana_Confirmation,Ana_UserInput,MESOffset --svcname={2} --port={3} --monport={4} --loglevel=debug --log={5}/{6}fitsviewer.log".format(fitshome, self.rohost, self.svcname, self.fitsviewer_port, self.fitsviewer_monport, self.loghome, self.hostname)

        # somebody broke astropy  &*%^^&%^&^&*%!!!
        command_line = "/home/gen2/bin/start_fitsview.sh"
        args = shlex.split(command_line)
        self.__execute(cmd=args, procname='fits viewer')

    def launch_statmon(self):
        ''' statmon '''
        self.logger.debug('starting statmon...')
        os.environ['RO_NAMES'] = self.rohost
        gen2home = self.get_gen2home()

        command_line = "{0}/statmon/statmon.py --monport=34945 --loglevel=0".format(gen2home)
        args = shlex.split(command_line)
        self.__execute(cmd=args, procname='statmon')

    def launch_skycat(self):
        ''' skycat '''
        command_line = "wish8.4 /usr/local/lib/skycat3.1.2/main.tcl"
        args = shlex.split(command_line)
        self.__execute(cmd=args, procname='skycat')

    def launch_ds9(self):
        ''' ds9 '''
        command_line = "/usr/local/bin/ds9 -port %s" %os.environ['DS9PORT']
        args = shlex.split(command_line)
        self.__execute(cmd=args, procname='ds9')

    def launch_terminal(self):
        ''' gnome-terminal '''
        self.__execute(cmd=["gnome-terminal",], procname='gnome-terminal')

    @property
    def workdir(self):
        return os.path.join('/work', self.propid)

    @property
    def datadir(self):
        return os.path.join('/data', self.propid)

    def __execute_obcp(self, obcp, cmd, insname=None):
        ''' execute obcp '''

        iter = self.buffer_log.get_start_iter()

        if not self.is_propid(self.propid):
            self.buffer_log.insert(iter, 'error: propid=%s\n' %str(self.propid))
            self.logger.error('error: propid=%s' %str(self.propid))
            return

        command_line = cmd  %(self.propid, obcp, self.datadir, self.workdir)
        args = shlex.split(command_line)

        self.logger.debug('%s cmd=%s' %(insname, args))

        error = self.process.execute(args)
        if not error:
            self.buffer_log.insert(iter, 'starting %s...\n' %(insname))
        else:
            self.buffer_log.insert(iter, 'error: %s. %s\n' %(insname, error))
            self.logger.error('error: launching %s.. %s'  %(insname, error))

    def launch_spcam(self):
        self.logger.debug('starting spcam....')

        obcp = 'OBCP08'
        cmd = "/home/spcam01/suprime/suprime.ana %s %s %s %s"
        insname = 'SPCAM'
        self.__execute_obcp(obcp, cmd, insname)

    def launch_hds(self):
        self.logger.debug('starting hds....')
        obcp = 'OBCP06'
        cmd = "/home/hds01/hds.ana %s %s %s %s"
        insname = 'HDS'
        self.__execute_obcp(obcp, cmd, insname)

    def launch_ircs(self):
        self.logger.debug('starting ircs....')

        obcp = 'OBCP01'
        cmd = "/home/ircs01/ircs/ircs.ana %s %s %s %s"
        insname = 'IRCS'
        self.__execute_obcp(obcp, cmd, insname)

    def launch_focas(self):
        self.logger.debug('starting focas....')

        obcp = 'OBCP05'
        cmd = "/home/focas01/focas.ana %s %s %s %s"
        insname = 'FOCAS'
        self.__execute_obcp(obcp, cmd, insname)

    def launch_moircs(self):
        self.logger.debug('starting moircs....')
        obcp = 'OBCP17'
        cmd = "/home/moircs01/moircs/moircs.ana %s %s %s %s"
        insname = 'MOIRCS'
        self.__execute_obcp(obcp, cmd, insname)

    def launch_comics(self):
        self.logger.debug('starting comics....')
        obcp = 'OBCP07'
        cmd = "/home/comics01/comics/comics.ana %s %s %s %s"
        insname = 'COMICS'
        self.__execute_obcp(obcp, cmd, insname)


def get_portnum(hostname, options, logger):

    inc = 10

    ports = {'sum01': (options.port, options.monport , options.ds9port),
             'sum02': (options.port+inc , options.monport+inc , options.ds9port+inc),
             'hilo01': (options.port+inc*2 , options.monport+inc*2 , options.ds9port+inc*2),
             'mtk01': (options.port+inc*3 , options.monport+inc*3 , options.ds9port+inc*3), }

    try:
        port, monport, ds9port = ports[hostname]
    except Exception as e:
        port = options.port+inc*10
        monport = options.monport+inc*10
        ds9port = options.ds9port+inc*10

    logger.debug('port=%d monport=%d ds9port=%d' %(port, monport, ds9port))
    return (port, monport, ds9port)

def get_svcname(hostname, logger):

    svcnames = {'sum01': 'ANA', 'sum02': 'ANA2',
                'hilo01':'ANA3', 'mtk01':'MTK'}

    try:
        svcname = svcnames[hostname]
    except Exception as e:
        svcname = 'ANA10'

    logger.debug('svcname=%s' %svcname)
    return svcname

def main(options, args):

    hostname = args[0]

    if not options.logstderr:
        options.logfile = os.path.join(os.environ['HOME'],
                                       '%s-menu.log' % hostname)
    logger = ssdlog.make_logger(hostname, options)

    svcname = get_svcname(hostname, logger)

    port, monport, ds9port = get_portnum(hostname, options, logger)

    rohost = options.rohost

    os.environ['IMTDEV'] = "inet:%d" % ds9port
    os.environ['IMTDEV2'] = "inet:%d" % (ds9port+1)
    os.environ['DS9PORT'] = '%d' % ds9port

    logger.debug('svcname=%s fitsviewer port=%s monport=%s ds9_port=%s' % (
        svcname, port, monport, ds9port))

    def SigHandler(signum, frame):
        """Signal handler for all unexpected conditions."""
        logger.debug('signal handling.  %s' %str(signum))
        #update_menu_num(menu_file, num_menu-1, logger=logger)
        #ana.quit('quit')

    # Set signal handler for signals.  Add any other signals you want to
    # handle or terminate here.
    for sig in [signal.SIGINT, signal.SIGTERM, signal.SIGHUP]:
        signal.signal(sig, SigHandler)

    app = Widgets.Application(logger=logger)
    root = app.make_window(title='ANA Menu')

    try:
        ana = AnaMenu(root, logger, svcname, rohost, port, monport, hostname)
        ana.setup_ui()
        root.show()

        app.mainloop()

    except KeyboardInterrupt as e:
        print('interrupted by keyboard....')
        logger.debug('Keyboard Interrupt...')
        ana.quit('quit')
        app.quit()

    except Exception as e:
        logger.error('error: starting anamenu. %s' % e)
        #sys.exit(1)
        raise
