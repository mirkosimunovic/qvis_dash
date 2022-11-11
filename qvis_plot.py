import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from datetime import time as timefunc
import plotly.express as px

# the visibility plots will ignore times after this hour in the morning
morning_cut = timefunc(9, 0)
# the visibility plots will ignore times before this hour in the evening
evening_cut = timefunc(17, 54)

class Plot:
    def __init__(self, df, start_date, end_date, end_date_user, db):

        self.schedpath_text = db.schedpath_text
        self.df = df
        self.queuenightschedule_df = db.queuenightschedule_df
        self.nightvis_info = {}
        self.sdate = start_date
        self.edate = end_date
        self.edate_user = end_date_user
        self.nights_list = self.get_nights_list()
        self.break_values = self.get_break_values()
        self.request_windows = [(mindate, maxdate) for mindate, maxdate in zip(
            self.df.envcfg_lower_time_limit, self.df.envcfg_upper_time_limit)]
        self.load_windows(db.database)
        self.longdf = self.get_longdf()

        # Initialize the user input options
        self.longdf_user = self.longdf
        self.pgms_select = []
        self.timewindow_obs = False
        self.use_filter_schedule = True

    def get_nights_list(self):
        nights = pd.date_range(
            self.sdate.date(), self.edate_user.date(), freq='1D', tz=None)
        if self.queuenightschedule_df is not None:  # case when using only queue nights
            nights = [night for night in nights if night.date(
            ) in self.queuenightschedule_df['obs_night'].dt.date.values]
        return nights

    def get_break_values(self):
        time = self.sdate
        obsnights = self.queuenightschedule_df['obs_night'].dt.date.values
        break_list = []

        while time <= self.edate:
            if time.date() not in obsnights:
                d = time.date()
                break_list.append(datetime(d.year, d.month, d.day, 18, 0))
            time = time+timedelta(days=1)

        return break_list

    def load_windows(self, database):

        time = self.sdate
        while time <= self.edate:
            self.nightvis_info[time.strftime(
                "%y-%m-%d")] = database[time.strftime("%y-%m-%d")]
            time = time + timedelta(days=1)

    def get_longdf(self):

        self.longdf = pd.DataFrame(columns=list(
            self.df.columns.values)+['start', 'end'])

        def this_key(i, program, this_df):
            return program+this_df.target_name[i]+this_df.envcfg_moon[i]+str(this_df.envcfg_moon_sep[i])+str(self.request_windows[i][0])+str(self.request_windows[i][1])

        time = self.sdate
        while time <= self.edate_user:

            tonight_df = self.df.copy()
            tonight_df['start'], tonight_df['end'] = np.zeros(
                tonight_df.shape[0]), np.zeros(tonight_df.shape[0])

            nw = self.nightvis_info[time.strftime('%y-%m-%d')]
            targ_dic = nw['targ_dic']

            # Only get visibility windows if night is within the queried period (case of schedule only)
            if pd.Timestamp(time.date()) in self.nights_list:

                start_list = [targ_dic[this_key(
                    i, program, self.df)]['window_start'] for i, program in enumerate(self.df.program)]
                end_list = [targ_dic[this_key(
                    i, program, self.df)]['window_end'] for i, program in enumerate(self.df.program)]
                tonight_df['start'] = start_list
                tonight_df['end'] = end_list

                self.longdf = pd.concat(
                    [self.longdf, tonight_df.copy()], axis=0, ignore_index=True)

            time = time + timedelta(days=1)

        # remove rows of OBs that have no observable windows.
        self.longdf = self.longdf.dropna(subset=['start'])

        # Get the observing night. Subtract 1 day for OBs that start after midnight.
        self.longdf['Date'] = pd.to_datetime(self.longdf.start.apply(lambda x: x.date(
        )-timedelta(days=1) if x.time() < datetime(2000, 1, 1, 12, 0, 0).time() else x.date()))

        # Sort order of OBs to follow grade and program name in order.
        self.longdf.sort_values(
            by=['grade', 'program'], ascending=True, inplace=True)

        return self.longdf

    def update_longdf(self, pgms, timewindow_obs, use_filter_schedule):

        if pgms != self.pgms_select or use_filter_schedule != self.use_filter_schedule or timewindow_obs != self.timewindow_obs:

            self.pgms_select = pgms
            self.timewindow_obs = timewindow_obs
            self.use_filter_schedule = use_filter_schedule

        else:
            return

        longdf = self.longdf.copy()
        # Filter by user input program list
        longdf = longdf[longdf.program.isin(self.pgms_select)]

        if self.timewindow_obs == True:       # Filter OBs with time windows

            longdf = longdf[~pd.isnull(longdf.envcfg_lower_time_limit) | ~pd.isnull(
                longdf.envcfg_upper_time_limit)]

        if self.use_filter_schedule == True:    # Filter OBs with available filters each night

            schedule = self.queuenightschedule_df.copy(deep=True)
            schedule['filters'] = schedule['filters'].str.split(',').apply(
                lambda x: [val.lower().strip() for val in x])    # make lower case and turn into python list

            idx = longdf.apply(
                lambda x: x['inscfg_filter'] in schedule.loc[schedule['obs_night'] == x['Date']]['filters'].iloc[0], axis=1)
            if len(idx) > 0:
                longdf = longdf.loc[idx]
            else:
                longdf = longdf.loc[[]]

        self.longdf_user = longdf

    def fill_plot(self):

        longdf = self.longdf_user

        minn = min(self.nights_list).date()
        maxx = max(self.nights_list).date()+timedelta(days=1)

        fig = px.timeline(longdf, x_start="start", x_end="end",
                          y="name",
                          color=self.groupby,
                          template="simple_white",
                          hover_data={'program': True, 'grade': True, 'inscfg_filter': True, 'envcfg_seeing': True,
                                      'envcfg_transparency': True, 'envcfg_moon': True, 'target_name': True},
                          labels={'inscfg_filter': 'filter', 'envcfg_seeing': 'seeing',
                                  'envcfg_transparency': 'transp', 'envcfg_moon': 'moon', 'target_name': 'target'},
                          range_x=[datetime(minn.year, minn.month, minn.day, evening_cut.hour, evening_cut.minute),
                                   datetime(maxx.year, maxx.month, maxx.day, morning_cut.hour, morning_cut.minute)])

        time = self.sdate
        draw = True
        while time <= self.edate:
            if draw == True:
                nw = self.nightvis_info[time.strftime("%y-%m-%d")]
                # Draw the sunrise/sunset +-30 min limits
                fig.add_vrect(x0=nw['sunrise']-timedelta(minutes=30), x1=nw['sunset'] +
                              timedelta(minutes=30), line_width=0, fillcolor="gray")

            if pd.Timestamp(time.date()) in self.nights_list:
                draw = True
            else:
                draw = False

            time = time + timedelta(days=1)
            continue

        fig.update_xaxes(
            rangebreaks=[{'pattern': 'hour', 'bounds': [morning_cut.hour+morning_cut.minute/60., evening_cut.hour+evening_cut.minute/60.]},
                         {'values': self.break_values}

                         ])
        fig.update_layout(xaxis=dict(dtick=86400000.0, tickformat='%b-%d %H:%M'),
                          xaxis_title="Time (HST)"
                          )

        fig.add_annotation(x=0.01, y=1.03,
                           xref='paper', yref='paper',
                           text="Queue Nights Only. Limits are 30 min after/before sunset/sunrise. ",
                           showarrow=False,
                           )

        return fig

    def fill_plot_prog(self):

        longdf = self.longdf_user

        pgms = longdf.program.unique()
        # create mapping dict from program column
        mapping_prog = {item: i for i, item in enumerate(pgms)}
        # define the Y value using the program # of each OB
        Yval = longdf['program'].apply(lambda x: mapping_prog[x])
        Yval_offset = Yval
        for pgm in pgms:
            df = longdf.loc[longdf.program == pgm]
            # create mapping dict from groupping column
            mapping = {item: i for i, item in enumerate(
                df[self.groupby].unique())}
            # define an offset value using the group id number of each OB in this program
            offsets = df[self.groupby].apply(lambda x: mapping[x])
            # offset values have to center in zero
            offsets = offsets-((len(mapping)-1)/2.0)
            # offset values have to be normalized to maximum 0.3 deviation from axis tick
            offsets = offsets/max(1, max(offsets))*0.35
            # add the offsets accordingly to each OB based on their unique index of the original DataFrame.
            Yval_offset = Yval_offset.add(offsets, fill_value=0)
        longdf['Yval_offset'] = Yval_offset

        minn = min(self.nights_list).date()
        maxx = max(self.nights_list).date()+timedelta(days=1)

        fig = px.timeline(longdf, x_start="start", x_end="end",
                          y='Yval_offset',
                          color=self.groupby,
                            template="simple_white",
                            range_x=[datetime(minn.year, minn.month, minn.day, evening_cut.hour, evening_cut.minute),
                                     datetime(maxx.year, maxx.month, maxx.day, morning_cut.hour, morning_cut.minute)],
                            hover_data={'Yval_offset': False, 'program': True, 'grade': True, 'inscfg_filter': True,
                                        'envcfg_seeing': True, 'envcfg_transparency': True, 'envcfg_moon': True, 'target_name': True},
                            labels={'inscfg_filter': 'filter', 'envcfg_seeing': 'seeing', 'envcfg_transparency': 'transp', 'envcfg_moon': 'moon', 'target_name': 'target'})

        time = self.sdate
        draw = True
        while time <= self.edate:
            if draw == True:
                nw = self.nightvis_info[time.strftime("%y-%m-%d")]
                fig.add_vrect(x0=nw['sunrise']-timedelta(minutes=30), x1=nw['sunset'] +
                              timedelta(minutes=30), line_width=0, fillcolor="gray")

            if pd.Timestamp(time.date()) in self.nights_list:
                draw = True
            else:
                draw = False

            time = time + timedelta(days=1)
            continue

        fig.update_xaxes(
            rangebreaks=[{'pattern': 'hour', 'bounds': [morning_cut.hour+morning_cut.minute/60., evening_cut.hour+evening_cut.minute/60.]},
                         {'values': self.break_values},
                         ])
        fig.update_layout(xaxis=dict(dtick=86400000.0, tickformat='%b-%d %H:%M'),
                          xaxis_title="Time (HST)",
                          yaxis_title='program'
                          )

        fig.update_yaxes(range=[-0.6, len(pgms)-0.4],
                         tickvals=[k for k in range(len(pgms))],
                         ticktext=[pgm for pgm in pgms]
                         )
        fig.update_traces(width=0.35)

        fig.add_annotation(x=0.01, y=1.03,
                           xref='paper', yref='paper',
                           text="Queue Nights Only. Limits are 30 min after/before sunset/sunrise.",
                           showarrow=False,
                           )

        return fig

    def fill_plot_num(self):

        longdf = self.longdf_user

        bardata = longdf.groupby(['Date', self.groupby]).count()['id']

        fig = px.bar(bardata.unstack())

        fig.update_xaxes(
            rangebreaks=[
                {'values': [d.date() for d in self.break_values]}
            ])
        fig.update_layout(
            xaxis=dict(dtick=86400000.0),
            yaxis_title="Number of Observable OBs",
            xaxis_title='Date (HST)')
        fig.update_traces(width=5E7)

        return fig

    def fill_plot_TotTime(self):

        df = self.df.copy(deep=True)
        df.sort_values(by=['grade', 'program'], ascending=True, inplace=True)

        def add_text(fig):
            fig.add_annotation(x=0.03, y=1.02,
                               xref='paper', yref='paper',
                               text="All OBs found in Query. Observability is not considered",
                               showarrow=False,
                               )

        if self.groupby == 'inscfg_filter':
            grade_arr = df.grade.unique()
            bardata = df.groupby([self.groupby, 'grade'])['total_time'].sum().div(
                3600).unstack('grade')[list(grade_arr)]
            fig = px.bar(bardata)
            fig.update_layout(yaxis_title="Total Combined Time (hours)")
            add_text(fig)
            return fig

        elif self.groupby == 'program':
            filter_arr = df.inscfg_filter.unique()
            # The df DataFrame has already been sorted by (grade,program).
            sorted_arr = df.program.unique()
            bardata = df.groupby([self.groupby, 'inscfg_filter'])['total_time'].sum().div(
                3600).unstack('inscfg_filter')[list(filter_arr)].loc[list(sorted_arr)]
            fig = px.bar(bardata)
            fig.update_layout(yaxis_title="Total Combined Time (hours)")
            add_text(fig)
            return fig

        else:
            filter_arr = df.inscfg_filter.unique()
            bardata = df.groupby([self.groupby, 'inscfg_filter'])['total_time'].sum().div(
                3600).unstack('inscfg_filter')[list(filter_arr)]
            fig = px.bar(bardata)
            fig.update_layout(yaxis_title="Total Combined Time (hours)")
            add_text(fig)
            return fig

    def fill_plot_completion(self, horizontal=False):

        df = self.df.copy(deep=True)
        df.sort_values(by=['grade', 'program'], ascending=True, inplace=True)

        bardata = df.groupby(
            ['program', 'grade', 'completion_rate'], as_index=False, sort=False).mean()
        bardata['perc_frac'] = bardata['completion_rate'].div(100)

        if horizontal:
            fig = px.bar(bardata, y='program', x='completion_rate',
                         text='completion_rate', color='grade', orientation='h')
        if not horizontal:
            fig = px.bar(bardata, x='program', y='perc_frac',
                         text='completion_rate', color='grade')
            fig.update_layout(yaxis_title="Completion Rate",
                              yaxis_tickformat='.1%')

        return fig
