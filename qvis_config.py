import os
import yaml

#-------------------- HSC Queue Config ---------------------

#  The key must match 'inscfg_filter' in database ('nb' matches all 'nb*')
filters_dict = {
                'g':{'label':'HSC-g'},
                'r2':{'label':'HSC-r2'},
                'i2':{'label':'HSC-i2'},
                'z':{'label':'HSC-z'},
                'y':{'label':'HSC-Y'},
                'nb':{'label':'NB*'}
}

grade_dict = {
                'A':{'label':'Grade A'},
                'B':{'label':'Grade B'},
                'C':{'label':'Grade C'},
                'F':{'label':'Grade F'},
}

# seeing options must match 'envcfg_seeing' in database
seeing_options = ['0.8','1.0','1.3','1.6','100']

# transp options must match 'envcfg_transp' in database
transp_options = ['0.7','0.4','0.1','0.0']



#------------------  Spreadsheet files PATH -------------------

with open('qvis_config.yaml') as f:
    path_data = yaml.load(f,Loader=yaml.SafeLoader) 

progfile_path = path_data['progfile_path']
allprogfile_path = path_data['allprogfile_path']
qdbfile_path = path_data['qdbfile_path']
schedpath_text = path_data['schedpath_text']

# create database file in qvis_dash working directory
current_semester = path_data['current_semester']
database_path = os.path.join(path_data['database_path'],'database_'+current_semester+'.pickle')


#-------------------- App config ------------------------------
available_yaxis = ["OBs", "program", "number", "time sum", "completion"]
available_group = ['program', 'filter', 'grade', 'completion',
                   'seeing', 'airmass', 'transp', 'moon', 'moon_sep', 'target']
key_dic = {
    "program": "program",
    "filter": "inscfg_filter",
    "grade": "grade",
    "completion": "completion_rate",
    "seeing": "envcfg_seeing",
    "airmass": "envcfg_airmass",
    "transp": "envcfg_transparency",
    "moon": "envcfg_moon",
    "moon_sep": "envcfg_moon_sep",
    "target": "target_name"
}

# options for max number of OBs/program in Query
maxOBquery_arr = [10, 100, 300, 9999]
