from qplan import q_db, q_query
from qplan.entity import StaticTarget
from ginga.misc.log import get_logger

import traceback
import os
import pandas as pd
from datetime import datetime, timedelta

import qvis_config as cfg



class Call:
    def __init__(self, grade, seeing, transp, filters, sdate, edate, maxOBquery, timewindow_obs):

        self.grade = grade
        self.seeing = seeing
        self.transp = transp
        self.filters = filters
        self.sdate = datetime(sdate.year, sdate.month,
                              sdate.day)+timedelta(hours=12)
        self.edate = datetime(edate.year, edate.month,
                              edate.day)+timedelta(hours=36)
        self.edate_user = datetime(edate.year, edate.month,
                                   edate.day)+timedelta(hours=12)
        
        self.progfile_path = cfg.progfile_path
        self.allprogfile_path = cfg.allprogfile_path
        self.qdbfile = cfg.qdbfile_path

        self.maxOBquery = int(maxOBquery)
        self.timewindow_obs = timewindow_obs
        self.skipped_pgm = []

        try:
            self.connect()
            self.pgms = self.get_programs()
            self.obs = self.get_obs()
            self.obs = self.get_observable_obs()
            self.df, self.df_pgm = self.build_df()
            self.targets = [StaticTarget(name=name, ra=ra, dec=dec) for name, ra, dec in zip(
                self.df.target_name, self.df.target_ra, self.df.target_dec)]
            self.request_windows = [(mindate, maxdate) for mindate, maxdate in zip(
                self.df.envcfg_lower_time_limit, self.df.envcfg_upper_time_limit)]

        except Exception:
            traceback.print_exc()

    def connect(self):

        # create null logger
        logger = get_logger("example1", log_stderr=False)
        # config file for queue db access
        q_conf_file = os.path.join(os.path.abspath('.'), self.qdbfile)

        # create handle to queue database (be sure it is running at the chosen address)
        self.qdb = q_db.QueueDatabase(logger)
        try:
            self.qdb.read_config(q_conf_file)
        except Exception:
            traceback.print_exc()
        self.qdb.connect()

        # make query object
        self.qa = q_db.QueueAdapter(self.qdb)
        self.qq = q_query.QueueQuery(self.qa)

    def get_programs(self):

        # get programs by program spreadsheet file
        try:
            df = pd.read_excel(self.progfile_path, engine='openpyxl')
            # This will drop the rows where ALL elements are missing.
            df = df.dropna(how='all')
            active_pgms = list(df.proposal)
            self.pgms = [self.qq.get_program(prog) for prog in active_pgms]
        except Exception:
            traceback.print_exc()
            return None

        # Filter by Grade
        newpgms = []
        for pgm in self.pgms:
            if pgm.grade in self.grade:
                newpgms.append(pgm)
        self.pgms = newpgms

        # Get the completion rates
        self.pgms = self.get_completion_rates(self.pgms)

        return self.pgms

    def get_completion_rates(self, pgms):

        executedOBs = self.get_exec_OBs()
        for pgm in pgms:
            key = pgm.proposal
            if key not in executedOBs:
                pgm.completion_rate = 0.0
                pgm.used_time = 0.0
            else:
                tot_exec_time = sum(
                    [executedOBs[key][ob]['total_time'] for ob in executedOBs[key]])
                # Add the queue operation overhead time
                tot_used_time = (tot_exec_time+tot_exec_time/8.8*1.2)
                pgm.used_time = tot_used_time
                # rounded to 1 decimal place
                pgm.completion_rate = round(
                    tot_used_time/pgm.total_time*100., 1)

        return pgms

    def get_exec_OBs(self):

        executedOBs = list(self.qq.get_do_not_execute_ob_keys())
        pposals = [pgm.proposal for pgm in self.pgms]
        executedOBs = [OB for OB in executedOBs if OB[0] in pposals]
        if len(executedOBs) > 0:
            executedOBs = list(self.qq._ob_keys_to_obs(executedOBs))
        else:
            return []
        d = dict()
        for rec in executedOBs:
            dd = d.setdefault(rec['program'], dict())
            dd[rec['name']] = dict(total_time=rec['total_time'])
        executedOBs = d
        return executedOBs

    def get_obs(self):

        # Get semester OBs from spreadsheet files
        nofiles = []
        for pgm in self.pgms:
            try:
                xls = pd.ExcelFile(self.allprogfile_path +
                                   '/'+pgm.proposal+'.xlsx', engine='openpyxl')
                df1 = pd.read_excel(xls, 'ob')
                df1 = df1.loc[df1.Code.notna()]
                pgm.spsheet_obs = df1.Code.values
            except Exception:
                traceback.print_exc()
                nofiles.append(pgm.proposal)
                pgm.spsheet_obs = None

        # Get all OBs in all programs (first OB search including observed OBs)
        obs_all = []
        for pgm in self.pgms:
            prop = pgm.proposal
            pgm.obs = []
            obs = list(self.qq.get_obs_by_proposal(prop))
            for ob in obs:
                if pgm.spsheet_obs is not None and ob.name not in pgm.spsheet_obs:  # skip OB if not in semester spreadsheet
                    continue
                if self.is_ob_ok(ob):
                    # add the grade key to the OB object.
                    ob.grade = pgm.grade
                    # add the completion rate key to the OB object.
                    ob.completion_rate = pgm.completion_rate
                    obs_all.append(ob)
                    pgm.obs.append(ob)

        self.obs = obs_all
        # Use the qualifying OBs to update the Program list.
        self.update_pgms()
        return self.obs

    # Remove Programs from Program list that do not have any qualifying OBs.
    def update_pgms(self):

        newpgms = [ob.program.proposal for ob in self.obs]
        self.pgms = [pgm for pgm in self.pgms if pgm.proposal in newpgms]

    def get_observable_obs(self):

        # get OBs that can be observed (second OB search to exclude observed OBs)
        keys = list(self.qq.get_schedulable_ob_keys())
        keys_names = [key[1] for key in keys]
        obs_all = []
        pgm_count = {}
        for ob in self.obs:
            this_name = ob.name
            # Why am I using a list, and not an int counter??? Weird...
            num = pgm_count.setdefault(ob.program.proposal, [])
            if len(num) >= self.maxOBquery:        # skip an OB if it exceeds the Max OBs per program
                if ob.program.proposal not in self.skipped_pgm:
                    self.skipped_pgm.append(ob.program.proposal)
                continue
            if this_name in keys_names:
                num += [1, ]
                obs_all.append(ob)
        self.obs = obs_all
        return self.obs

    def is_ob_ok(self, ob):

        seeing = '%.1f' % ob.envcfg.seeing
        transp = '%.1f' % ob.envcfg.transparency
        mindate = ob.envcfg.lower_time_limit
        maxdate = ob.envcfg.upper_time_limit
        # Reject OB if not time critical
        if self.timewindow_obs and (mindate == None and maxdate == None):
            return False

        if ob.inscfg.filter.startswith('nb'):
            filter = 'nb'
        else:
            filter = ob.inscfg.filter.lower()  # make lower case
        if seeing in self.seeing:   # seeing must be exactly same
            if transp in self.transp:   # transp must be exactly same
                if (filter in self.filters):    # Filters must be exactly same
                    return True

        return False

    def build_df(self):

        df = {}
        for ob in self.obs:
            dictionary = ob.to_rec()
            for key in dictionary:
                if key.startswith('calib'):     # ignore the 'calib_*' entries.
                    continue
                if type(dictionary[key]) is dict:
                    for key2 in dictionary[key]:
                        if key+'_'+key2 in df:  # check if key already in DataFrame dictionary
                            # add new element to list
                            df[key+'_'+key2] += [dictionary[key][key2], ]
                        else:
                            # create the columns and add elements
                            df[key+'_'+key2] = [dictionary[key][key2]]
                else:
                    if key in df:               # check if key already in DataFrame dictionary
                        # add new element to list
                        df[key] += [dictionary[key], ]
                    else:
                        # create the columns and add elements
                        df[key] = [dictionary[key]]

        df = pd.DataFrame(df)
        # Retrieve the grade column and move it to the front
        grades = df['grade']
        df.drop('grade', axis=1, inplace=True)
        df.insert(2, 'grade', grades)
        self.df = df

        df2 = {}
        for pgm in self.pgms:
            dictionary2 = pgm.to_rec()
            for key in dictionary2:
                mylist = df2.setdefault(key, [])
                mylist.append(dictionary2[key])
        self.df_pgm = pd.DataFrame(df2)
        self.df_pgm.sort_values(
            by=['grade', 'proposal'], ascending=True, inplace=True)

        return self.df, self.df_pgm
