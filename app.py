from datetime import datetime, timedelta
import dash
from dash import dcc, html, callback_context
import dash_bootstrap_components as dbc
from datetime import date
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

import qvis_config as cfg
import app_functions as fct

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server
app.title = 'HSC QVis'

app.pgms = []
app.pgm_select = []

checklist_grade = dcc.Checklist(
    id='grade-checklist',
    options=[{'label': dic['label'], 'value':key}
             for key, dic in cfg.grade_dict.items()],
    labelStyle={'display': 'block'},
    value=['A', 'B']
)

checklist_seeing = dcc.Checklist(
    id='seeing-checklist',
    options = cfg.seeing_options,
    labelStyle={'display': 'block'},
    value = cfg.seeing_options
)

checklist_transp = dcc.Checklist(
    id='transp-checklist',
    options = cfg.transp_options,
    labelStyle={'display': 'block'},
    value = cfg.transp_options
)

checklist_filter = dcc.Checklist(
    id='filter-checklist',
    options=[{'label':dic['label'],'value':key}
            for key,dic in cfg.filters_dict.items()],
    labelStyle={'display': 'block'},
    value=[filter for filter in cfg.filters_dict.keys()]
)

datepicker1 = dcc.DatePickerSingle(
    id='my-date-picker-single',
    initial_visible_month=date.today(),
    date=date.today(),
)

datepicker2 = dcc.DatePickerSingle(
    id='my-date-picker-single2',
    initial_visible_month=date.today()+timedelta(days=10),
    date=date.today()+timedelta(days=10),
)


tab1 = dbc.Card([
    dbc.CardBody([
                dbc.Row([
                    dbc.Col([
                        html.H5('Programs:'),
                        checklist_grade
                    ], width={'offset': 1}),
                    dbc.Col([
                        html.H5('Seeing:'),
                        checklist_seeing
                    ]),
                    dbc.Col([
                        html.H5('Transparency:'),
                        checklist_transp
                    ]),
                    dbc.Col([
                        html.H5('Filters:'),
                        checklist_filter
                    ]),
                    dbc.Col([
                        html.H5('From:'),
                        datepicker1,
                        html.Br(),
                        html.H5('Until:'),
                        datepicker2
                    ])
                ]),
                html.Div(
                    [
                        dbc.Button("Query OBs", id='button',
                                   color="primary", outline=True),
                    ],
                    className="d-grid gap-2 col-6 mx-auto",
                )
                ])
],style={'height':'15rem'}
)

tab2 = dbc.Card([
    dbc.CardBody([
                dbc.Row([
                    dbc.Col([
                        html.H5('Max OBs p/Program:'),
                        dcc.Slider(0, 3, 1, marks={i: '{}'.format(val) for i, val in enumerate(
                            cfg.maxOBquery_arr)}, value=2, id='maxOBs')
                    ]),
                    dbc.Col([
                        html.H5('Time Window:'),
                        dcc.Checklist(id='time-window-only', options=[
                                      {'label': 'Use *only* OBs with Time Window', 'value': 1}], value=[0])
                    ]),
                    dbc.Col([
                        html.H5('Queue Schedule:'),
                        dcc.Checklist(id='use-filter-schedule', options=[
                                      {'label': 'Use HSC filter availability', 'value': 1}], value=[1])
                    ])

                ])
                ])
],style={'height':'15rem'}
)


tab3 = dbc.Card([
    dbc.CardBody([
                dbc.Row(id='summary-tab')
                ])
],style={'height':'15rem'}
)

app.layout = html.Div([
    html.Br(),
    html.H1('HSC Queue Visualization', style={
            'color': 'blue', 'textAlign': 'center'}),
    dbc.Row([
        dbc.Col([
            dbc.Tabs(id='query-tabs',active_tab='1',
                      children=[dbc.Tab(tab1, label='Query',tab_id='1'),
                      dbc.Tab(tab2, label='Options',tab_id='2'),
                      dbc.Tab(tab3, label='Summary',tab_id='3'),
                      ])

        ], width={'size': 6, 'offset': 0}),
        dbc.Col([
            html.Br(),
            html.H5('Y-Axis'),
            dcc.Dropdown(
                id='y-axis',
                options=[{'label': i, 'value': i}
                         for i in cfg.available_yaxis],
                value='OBs'
            ),
            html.H5('Group by'),
            dcc.Dropdown(
                id='groupby',
                options=[{'label': i, 'value': cfg.key_dic[i]}
                         for i in cfg.available_group],
                value='program'
            ),
            html.H5('Filter Programs:'),
            dcc.Dropdown(id='pgm-dropdown',
                         options=app.pgms,
                         value=app.pgm_select,
                         multi=True
                         ),
        ], width={'size': 6, 'offset': 0}),
    ], className="mx-5"),
    dbc.Card([dbc.CardBody([html.P(id='log')])]),
    html.Br(),
    dcc.Loading([html.Div(id='chart')]),
    html.Br(),
    dbc.Tabs(id='table-tabs',active_tab='1',children=[
                            dbc.Tab(label='Queried OBs',tab_id='1'),
                            dbc.Tab(label='Observable OBs',tab_id='2'),
                            dbc.Tab(label='Queue Schedule',tab_id='3')
                            ]),
    html.Div(id='datatable')
]
)

@app.callback(
    Output('my-date-picker-single2','min_date_allowed'),
    Input('my-date-picker-single','date')
    )
def limit_date_range(date_value):
    return date_value

@app.callback(
    Output('chart', 'children'),
    Output('pgm-dropdown', 'options'),
    Output('pgm-dropdown', 'value'),
    Output('log','children'),
    Input('button', 'n_clicks'),
    Input('y-axis', 'value'),
    Input('groupby', 'value'),
    Input('pgm-dropdown', 'value'),
    Input('time-window-only', 'value'),
    Input('use-filter-schedule', 'value'),
    State('grade-checklist', 'value'),
    State('seeing-checklist', 'value'),
    State('transp-checklist', 'value'),
    State('filter-checklist', 'value'),
    State('my-date-picker-single', 'date'),
    State('my-date-picker-single2', 'date'),
    State('maxOBs', 'value')
)
def update(n_clicks, display, groupby, pgms, timewindow_obs, use_filter_schedule, grade, seeing, transp, filters, date_value, date_value2, maxOBquery):

    sdate = datetime.strptime(date_value, '%Y-%m-%d')
    edate = datetime.strptime(date_value2, '%Y-%m-%d')
    timewindow_obs = True in timewindow_obs
    use_filter_schedule = True in use_filter_schedule
    maxOBquery = cfg.maxOBquery_arr[maxOBquery]

    if n_clicks is None:
        raise PreventUpdate

    # Execute only if callback triggered by Query button.
    if callback_context.triggered_id == 'button':
        app.call = fct.create_call(grade, seeing, transp, filters, sdate, edate,
                               maxOBquery=maxOBquery,
                               timewindow_obs=timewindow_obs
                               )
        app.db = fct.create_database(app.call)
        app.plot_obj = fct.make_plot_obj(
            app.call.df, app.call.sdate, app.call.edate, app.call.edate_user, app.db)
        app.pgms = list(app.plot_obj.longdf.program.unique())
        app.pgm_select = app.pgms.copy()

    if callback_context.triggered_id == 'pgm-dropdown':
        app.pgm_select = pgms

    app.log = fct.make_log(app.call,app.plot_obj)
    
    app.plotly_fig = fct.make_fig(app.plot_obj, display, groupby,
                              app.pgm_select, timewindow_obs, use_filter_schedule)

    

    return app.plotly_fig,  app.pgms, app.pgm_select, app.log

@app.callback(
    Output('summary-tab','children'),
    Output ('query-tabs','active_tab'),
    Input('log','children'),
    State('button','n_clicks')
)
def summary_tab(log,n_clicks):

    if n_clicks is None:
        raise PreventUpdate

    content = fct.get_summary_info(app.call,app.plot_obj)
    active_tab = '3'

    return content,active_tab


@app.callback(
    Output('datatable','children'),
    Input('table-tabs','active_tab'),
    Input('log', 'children'),    
    State('button','n_clicks')
)
def update_table(active_tab,log,n_clicks):

    if n_clicks is None:
        raise PreventUpdate
    if active_tab=='1':
        app.table = fct.get_table(app.plot_obj.df)
    elif active_tab=='2':
        app.table = fct.get_table(app.plot_obj.df.loc[app.plot_obj.df.name.isin(app.plot_obj.longdf_user.name)])
    elif active_tab=='3':
        app.table = fct.get_table(app.plot_obj.queuenightschedule_df)
        
    return app.table

if __name__=='__main__':

    app.run_server(host= '0.0.0.0',debug=False, port=8000)
