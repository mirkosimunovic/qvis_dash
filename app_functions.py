from dash import dcc, html, dash_table
import dash_bootstrap_components as dbc
import logging

import qplan_caller
import qvis_plot
import qvis_database

from argparse import ArgumentParser
import os
from ginga.misc import log




def get_logger():

    app_description = 'HSC Queue Vis Dash'
    argprs = ArgumentParser(description=app_description)
    log.addlogopts(argprs)
    (options, args) = argprs.parse_known_args([])

    # Environment variable LOGHOME on Gen2 machines is /home/gen2/Logs
    options.logfile = os.path.join(
        os.environ.get('LOGHOME', '/tmp'), 'qvis_dash.log')
    options.loglevel = logging.DEBUG  # or logging.INFO

    logger = log.get_logger(name='qvis_dash', options=options)
    return logger

logger = get_logger()


def create_call(grade, seeing, transp, filters, sdate, edate, maxOBquery, timewindow_obs):

    logger.info("Creating the Call object")
    call = qplan_caller.Call(grade, seeing, transp, filters, sdate, edate,
                 maxOBquery, timewindow_obs,logger)

    return call

def create_database(call):

    logger.info("Creating the DataBase object")
    db = qvis_database.DataBase(call,logger)
    return db


def make_plot_obj(df, sdate, edate, edate_user, db):

    logger.info("Creating the Plot object")
    plot = qvis_plot.Plot(df, sdate, edate, edate_user, db)
    return plot


def make_fig(plot_obj, display, groupby, pgms, timewindow_obs, use_filter_schedule):

    logger.info("Calling Plot functions in Plot object")

    if plot_obj.nights_list == []:    # return empty figure if no queue nights in period
        return []

    plot_obj.update_longdf(pgms, timewindow_obs, use_filter_schedule)

    plot_obj.groupby = groupby

    if display == "OBs":
        plotly_fig = plot_obj.fill_plot()
    elif display == "program":
        plotly_fig = plot_obj.fill_plot_prog()
    elif display == "number":
        plotly_fig = plot_obj.fill_plot_num()
    elif display == "time sum":
        plotly_fig = plot_obj.fill_plot_TotTime()
    elif display == "completion":
        plotly_fig = plot_obj.fill_plot_completion()

    plotly_fig.update_layout(
        title={
            'text': "click (double-click) on legend to remove (isolate) data",
            'x': 0.55,
            'xanchor': 'left'},
        height=1000)

    fig = dcc.Graph(figure=plotly_fig),

    return fig


def get_summary_info(call, plot_obj):

    logger.info("Creating the summary Tab")
    plotly_fig = plot_obj.fill_plot_completion(horizontal=True)
    plotly_fig.update_layout(
        height=240,
        xaxis_title=None,
        yaxis_title=None,
        margin=dict(t=0, b=0, r=0, l=0)
    )
    plotly_fig.update_yaxes(autorange='reversed')

    fig = dcc.Graph(figure=plotly_fig,
                    config={'displayModeBar': False}
                    )
    # Get the programs DataFrame
    df = call.df_pgm[['proposal', 'grade',
                      'total_time', 'used_time', 'completion_rate']].copy(deep=True)

    df.loc[:,'total_time'] = df['total_time'].div(3600)
    df.loc[:,'used_time'] = df['used_time'].div(3600)
    df.loc[:, 'Remain[hr]'] = df['total_time'] - df['used_time']
    df = df[['proposal', 'grade', 'total_time', 'used_time',
             'Remain[hr]', 'completion_rate']]   # Re arrange order
    # round to 2 decimals
    df = df.round({'total_time': 2, 'used_time': 2, 'Remain[hr]': 2})
    df = df.rename(
        columns={'proposal': 'Program', 'total_time': 'Alloc[hr]', 'used_time': 'Used[hr]', 'completion_rate': 'Completion'})

    layout = [
        dbc.Col([
            html.Div(get_table(df, virtualization=False, height='220px', lineHeight='12px',
                     minwidth=0, maxwidth=0, tooltip_duration=0, sort_action='none'))
        ], width={'size': 7}),
        dbc.Col([
            html.Div(fig)
        ], width={'size': 5})
    ]

    return layout

def get_table(df, virtualization=True, height='500px', lineHeight='20px', sort_action='native', minwidth='90px', maxwidth='90px', tooltip_duration=None):

    table = dash_table.DataTable(
        columns=[
            {"name": i, "id": i} for i in df
        ],
        data=df.to_dict('records'),
        fixed_rows={'headers': True},
        virtualization=virtualization,
        tooltip_data=[
            {
                column: {'value': str(value), 'type': 'markdown'}
                for column, value in row.items()
            } for row in df.to_dict('records')
        ],
        style_table={'height': height},
        tooltip_delay=0,
        tooltip_duration=tooltip_duration,
        sort_action=sort_action,
        # filter_action='native',
        style_cell={'minWidth': minwidth,
                    'maxWidth': maxwidth, 'lineHeight': lineHeight},
        style_data={'lineHeight': lineHeight},
        style_data_conditional=[{'if': {'column_id': 'grade'}, 'minWidth': '35px', 'width': '35px', 'maxWidth': '35px'},
                                {'if': {'column_id': 'Program'}, 'minWidth': '130px', 'width': '130px', 'maxWidth': '130px'}]
    )

    return table

def make_log(call, plot_obj):

    logger.info("Creating the log widget in dashboard")
    Nquery = plot_obj.df.shape[0]
    Nobservable = plot_obj.longdf_user.name.unique().shape[0]
    queue_nights = len(plot_obj.nights_list) > 0
    log = 'Queried OBs: {} | Observable OBs: {}'.format(Nquery, Nobservable)
    layout = [html.P(log)]

    # check if max limit of OBs was reached for programs
    if len(call.skipped_pgm) > 0:
        warning = '== Warning: Max Limit of OBs ({}) was reached in: {}'.format(
            call.maxOBquery, call.skipped_pgm)
        layout += [html.P(warning), ]
    # check if no Queue nights in period
    if not queue_nights:
        error = '== ERROR: No Queue Nights in selected Period!'
        layout += [html.P(error), ]

    return layout



