import traceback
from datetime import time as timefunc
from datetime import  timedelta
from qplan.util.site import get_site
import pytz
local = pytz.timezone("US/Hawaii")
subaru = get_site('subaru')

import pickle
import pandas as pd

import qvis_config as cfg

minute_delta = 5   # frequency of elevation data in minutes
dark_moon_limit = 0.15   # maximum moon illumination fraction for 'dark' time
gray_moon_limit = 0.77   # maximum moon illumination fraction for 'gray' time

class DataBase:

    def __init__(self, call,logger):

        self.logger = logger
        self.database_path = cfg.database_path
        self.load_database()
        self.call = call
        self.schedpath_text = cfg.schedpath_text
        self.queuenightschedule_df = self.get_schedule_df()
        self.sdate = call.sdate
        self.edate = call.edate
        self.nightvis_info = self.get_windows()
        self.save_database()

    def load_database(self):
        try:
            f = open(self.database_path, 'rb')
            database = pickle.load(f)
            f.close()
        except Exception:
            self.logger.exception("Exception occurred")
            traceback.print_exc()
            database = {}

        self.database = database

    def save_database(self):

        # Update the values of keys of night data that was collected in the call
        for date in self.nightvis_info.keys():
            # Transform night_window object to dictionary to get attributes only
            self.database[date] = self.nightvis_info[date].__dict__

        with open(self.database_path, 'wb') as f:
            pickle.dump(self.database, f)

    def get_windows(self):

        nightvis_info = {}
        time = self.sdate
        while time <= self.edate:
            nw = night_window(time, self.call.df, self.call.targets, self.call.request_windows,
                              self.queuenightschedule_df, self.database)
            nightvis_info[time.strftime("%y-%m-%d")] = nw
            time = time + timedelta(days=1)

        return nightvis_info

    def get_schedule_df(self):
        try:
            df = pd.read_excel(self.schedpath_text, engine='openpyxl')
        except Exception:
            self.logger.exception("Exception occurred")
            df = None
            return df
        # drop the rows where ALL elements are missing
        df = df.dropna(how='all')
        df["start_dt"] = pd.to_datetime(
            df['date'].astype(str)+' '+df['start time'].astype(str))
        df["end_dt"] = pd.to_datetime(
            df['date'].astype(str)+' '+df['end time'].astype(str))
        df['start_dt'] = df['start_dt'].dt.tz_localize(local)
        df['end_dt'] = df['end_dt'].dt.tz_localize(local)
        df = df.sort_values(by='start_dt', ascending=True, ignore_index=True)
        df['start_dt'] = df.apply(lambda x: x['start_dt']+timedelta(days=1)
                                  if x['start_dt'].time() < timefunc(8, 0) else x['start_dt'], axis=1)
        df['end_dt'] = df.apply(lambda x: x['end_dt']+timedelta(days=1)
                                if x['end_dt'].time() < timefunc(8, 0) else x['end_dt'], axis=1)
        df['obs_night'] = pd.to_datetime(df.apply(lambda x: x['start_dt'].date(
        )-timedelta(days=1) if x['start_dt'].time() < timefunc(8, 0) else x['start_dt'].date(), axis=1))
        return df


############################################################################################################
##########################################################################################################

class night_window:
    def __init__(self, sdate, df, targets, request_windows, queuenightschedule_df, database):

        self.use_queue_schedule = (queuenightschedule_df is not None)
        start = sdate.strftime("%Y-%m-%d %H:%M")
        self.start = subaru.get_date(start)
        self.end = self.start+timedelta(days=1)
        subaru.set_date(self.start)
        self.sunset = subaru.sunset()
        self.evt12 = subaru.evening_twilight_12()
        self.evt18 = subaru.evening_twilight_18()
        self.mot12 = subaru.morning_twilight_12()
        self.mot18 = subaru.morning_twilight_18()
        self.next_sunrise = subaru.sunrise()
        # a fix so that we get the sunrise of the same day, instead of next morning.
        subaru.set_date(self.start-timedelta(hours=12))
        self.sunrise = subaru.sunrise()
        if self.use_queue_schedule:
            self.queue_night_limits = self.get_queue_night_limits(
                queuenightschedule_df)

        date = sdate.date().strftime("%y-%m-%d")
        # Retrieves the data from database if it exists for this night.
        self.targ_dic = database[date]['targ_dic'] if date in database else {}
        self.targ_observable = []

        for i, target in enumerate(targets):

            observable = False
            visible = False
            SkyOk = False
            if self.use_queue_schedule:
                time = self.queue_night_limits[0]
            else:
                time = self.sunset
            target_min_el = df.telcfg_min_el[i]
            max_airmass = df.envcfg_airmass[i]
            moon = df.envcfg_moon[i]
            moon_sep = df.envcfg_moon_sep[i]
            this_key = df.program[i]+df.target_name[i]+moon + \
                str(moon_sep) + \
                str(request_windows[i][0])+str(request_windows[i][1])
            if not this_key in self.targ_dic:

                self.targ_dic[this_key] = {}

                while (time < self.end):

                    info = subaru.calc(target, subaru.get_date(
                        time.strftime("%Y-%m-%d %H:%M")))
                    if not self.inside_time_window(time, request_windows[i]):
                        time = time + timedelta(minutes=minute_delta)
                        continue
                    if not SkyOk:
                        if self.sky_ok(info, moon_sep, moon):
                            SkyOk = True
                    if info.alt_deg >= target_min_el and info.airmass <= max_airmass and SkyOk and not visible:
                        self.targ_dic[this_key]['window_start'] = time
                        observable = True
                        visible = True
                    if info.airmass > max_airmass and visible:
                        self.targ_dic[this_key]['window_end'] = time
                        break
                    if info.alt_deg < target_min_el and visible:
                        self.targ_dic[this_key]['window_end'] = time
                        break
                    if time >= self.next_sunrise and visible:
                        self.targ_dic[this_key]['window_end'] = time
                        break
                    if self.use_queue_schedule and visible:
                        if time >= self.queue_night_limits[1]:
                            self.targ_dic[this_key]['window_end'] = time
                            break
                    if time >= self.queue_night_limits[1] and not visible:
                        break
                    if time >= self.next_sunrise and not visible:
                        break
                    if SkyOk:
                        if not self.sky_ok(info, moon_sep, moon):
                            self.targ_dic[this_key]['window_end'] = time
                            break
                    time = time + timedelta(minutes=minute_delta)

                if not observable:
                    self.targ_dic[this_key]['window_start'] = None
                    self.targ_dic[this_key]['window_end'] = None

            elif not self.targ_dic[this_key]['window_start'] == None:
                observable = True

            self.targ_observable.append(observable)
            print("  ", self.start.strftime("%m-%d-%Y....."),
                  str(i+1).rjust(4), "OBs done", end='\r')

    def sky_ok(self, info, moon_sep, moon):
        if moon == 'dark' and self.dark_time(info, moon_sep):
            return True
        if moon == 'gray' and (self.dark_time(info, moon_sep) or self.gray_time(info, moon_sep)):
            return True
        return False

    def dark_time(self, info, moon_sep):
        if info.moon_pct <= dark_moon_limit or info.moon_alt <= 0:
            if info.moon_sep >= moon_sep:
                return True
        return False

    def gray_time(self, info, moon_sep):
        if info.moon_pct <= gray_moon_limit and info.moon_alt > 0:
            if info.moon_sep >= moon_sep:
                return True
        return False

    def inside_time_window(self, time, request_windows):
        if pd.isnull(request_windows[0]) and pd.isnull(request_windows[1]):
            return True
        elif (not pd.isnull(request_windows[0])) and (not pd.isnull(request_windows[1])):
            mindate, maxdate = request_windows[0].astimezone(
                local), request_windows[1].astimezone(local)
            if time >= mindate and time <= maxdate:
                return True
            else:
                return False
        elif pd.isnull(request_windows[0]) and (not pd.isnull(request_windows[1])):
            maxdate = request_windows[1].astimezone(local)
            if time <= maxdate:
                return True
        elif (not pd.isnull(request_windows[0])) and pd.isnull(request_windows[1]):
            mindate = request_windows[0].astimezone(local)
            if time >= mindate:
                return True
        return False

    def get_queue_night_limits(self, df):
        df = df.loc[(self.sunset <= df['start_dt']) &
                    (self.next_sunrise >= df['end_dt'])]
        # No Queue runs tonight...
        if len(df) == 0:
            # This makes the While Loop end before starting, and on to the next night...
            return (self.end, self.end)
        else:
            # in case there are more than 1 queue windows in the same night
            return (df.start_dt.min(), df.end_dt.max())
