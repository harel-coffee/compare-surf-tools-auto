# -*- coding: utf-8 -*-
#
# @author Nikhil Bhagawt
# @date 1 Feb 2019

import numpy as np
import pandas as pd

def filter_data(data_df, subject_ID_col, qc_df, qc_criterion, external_criterion):
    """ Returns a subset of dataframe based on manual or automatic QC/outlier detection. 
    Also removes subjects based on external criteria such as minimum subjects per site. 
    """
    qc_type = qc_criterion[0] 
    qc_ind = qc_criterion[1] 
    print('\nFiltering based on {}. Number subjects before filtering {}'.format(qc_type,len(data_df[subject_ID_col].unique())))

    keep_subs = qc_df[qc_df[qc_type].isin(qc_ind)][subject_ID_col].unique()
    filtered_df = data_df[pd.to_numeric(data_df[subject_ID_col]).isin(keep_subs)]
    filtered_subs = filtered_df[subject_ID_col].unique()
    print('Resultant number of subjects {}'.format(len(filtered_subs)))
            
    # Check for minimum sample size requirement for covariates, especially SITE_ID
    if external_criterion != None:
        print('Filtering based on external crierion')
        for covar in external_criterion.keys():
            min_sample_req = external_criterion[covar] 
            print('Performing min sample (N_min={}) per workflow size check based on {}'.format(min_sample_req,covar))

            counts = filtered_df[covar].value_counts()
            filtered_df = filtered_df[filtered_df[covar].isin(counts[counts > min_sample_req].index)]
            print("Dropping subjects for all workflows for {} {}".format(covar,counts[counts <= min_sample_req]))
            filtered_subs = filtered_df[subject_ID_col].unique()
            print('Resultant number of subjects {}'.format(len(filtered_subs)))
            
    return filtered_df

def combine_processed_data(data_dict, subject_ID_col, na_action, data_label='software'):
    """ Reads CSV outputs from the processed MR images by software such as FreeSurfer, ANTs, CIVET, etc.
    """ 
    n_datasets = len(data_dict)
    print('Number of datasets: {}'.format(n_datasets))
    
    # Find common columns and subjects
    print('Finding common subject and columns')
    common_cols = []
    common_subs = []
    for dataset_name in data_dict.keys():
        print('dataset : {}'.format(dataset_name))
        data = data_dict[dataset_name]
        
        # common cols
        if len(common_cols) == 0:
            common_cols = list(data.columns)
        else:
            common_cols = list(set(common_cols) & set(data.columns))
        
        # common subs
        if len(common_subs) == 0:
            common_subs = list(data[subject_ID_col].values)
        else:
            common_subs = list(set(common_subs) & set(data[subject_ID_col].values))
        print('common subs: {}'.format(len(common_subs)))

    common_roi_cols = common_cols[:] #.copy()
    common_roi_cols.remove(subject_ID_col)

    print('Number of common subjects and columns: {}, {}'.format(len(common_subs),len(common_cols)))

    # Create master df after checking dataframe for missing column names for values
    df_concat = pd.DataFrame()
    for dataset_name in data_dict.keys():
        print('\nchecking {} dataframe'.format(dataset_name))
        data = data_dict[dataset_name]
        # Select only the common cols and subs
        data = data[data[subject_ID_col].isin(common_subs)][common_cols]
        print('Shape of the dataframe based on common cols and subs {}'.format(data.shape))
        if check_processed_data(data,common_cols,na_action):
            print('Basic data check passed')
            data[data_label] = np.tile(dataset_name,len(data))
            df_concat = df_concat.append(data,sort=True)
            print('Shape of the concat dataframe {}'.format(df_concat.shape))

    return df_concat, common_subs, common_roi_cols

def check_processed_data(df,col_list,na_action):
    """ Checks if provided dataframe consists of required columns and no missing values
    """
    check_passed = True

    # Check columns
    df_cols = df.columns
    if set(df_cols) != set(col_list):
        check_passed = False
        print('Column names mismatched')

    # Check missing values
    n_missing = df.isnull().sum().sum()
    if n_missing > 0:
        print('Data contains missing {} values'.format(n_missing))
        if na_action == 'drop':
            print('Dropping rows with missing values')
        elif na_action == 'ignore':
            print('Keeping missing values as it is')
        else:
            print('Not adding this data into master dataframe')
            check_passed = False

    return check_passed

# Individual scripts to reformat / rename csvs from differnet pipelines
# CIVET 2.1
def standardize_civet_data(civet_data, subject_ID_col, dkt_roi_map):
    """ Takes df from ANTs output and stadardizes column names for both left and right hemi
        Uses dkt naming dictionary to map freesurfer names onto civet names
    """
    civet_cols = civet_data.columns
    civet_to_std_naming_dict = {}
    for col in civet_cols:
        if col != subject_ID_col:
            col_name,col_hemi = col.split('.',1)[0],col.split('.',1)[1]
            fs_name = dkt_roi_map[dkt_roi_map['CIVET']==col_name]['Freesurfer'].values[0]
            new_col_name = col_hemi + '_' + fs_name
            civet_to_std_naming_dict[col] = new_col_name
        
    civet_data_std = civet_data.rename(columns=civet_to_std_naming_dict)
    return civet_data_std

# ANTs
def standardize_ants_data(ants_data, subject_ID_col):
    """ Takes df from ANTs output and stadardizes column names for both left and right hemi
    """
    ants_useful_cols = ['Structure Name']
    ants_to_std_naming_dict = {}
    ants_to_std_naming_dict['Structure Name'] = subject_ID_col #'SubjID'
    for roi in ants_data.columns:
        prefix = None
        name_split = roi.split(' ')
        if name_split[0] == 'left':
            prefix = 'L'
        if name_split[0] == 'right':
            prefix = 'R'

        if prefix is not None:
            ants_useful_cols.append(roi)
            std_name = prefix + '_' + ''.join(name_split[1:])
            ants_to_std_naming_dict[roi] = std_name

    ants_data_std = ants_data[ants_useful_cols].copy()
    ants_data_std = ants_data_std.rename(columns=ants_to_std_naming_dict)
    
    # Splitting SubjID column to ignore site name
    _, ants_data_std[subject_ID_col] = ants_data_std[subject_ID_col].str.rsplit('_', 1).str

    return ants_data_std

# FS 5.1 and 5.3
def standardize_fs_data(fs_data, subject_ID_col):
    """ Takes df from FS output and stadardizes column names for both left and right hemi
    """
    fs_useful_cols = [subject_ID_col] #'SubjID'
    fs_col_renames = {}
    for roi in fs_data.columns:
        prefix = None
        name_split = roi.split('_')
        if name_split[0] in ['L','R']:
            roi_rename = name_split[0] + '_' + name_split[1]
            fs_useful_cols.append(roi_rename)
            fs_col_renames[roi] = roi_rename
            
    fs_data_std = fs_data.rename(columns=fs_col_renames).copy()

    # Splitting SubjID column to ignore site name
    _, fs_data_std[subject_ID_col] = fs_data_std[subject_ID_col].str.rsplit('_', 1).str
    return fs_data_std

# FS6.0 (CBrain)
def standardize_fs60_data(fs60_data_lh, fs60_data_rh, subject_ID_col, aparc='aparc'):
    """ Takes two dfs from FS output from CBrain and stadardizes column names for both left and right hemi
    """
    # Parse and combine fs60 left and right data
    
    fs60_data_lh = fs60_data_lh.rename(columns={'lh.{}.thickness'.format(aparc):subject_ID_col})
    fs60_data_rh = fs60_data_rh.rename(columns={'rh.{}.thickness'.format(aparc):subject_ID_col})
    
    fs60_data = pd.merge(fs60_data_lh, fs60_data_rh, on=subject_ID_col, how='inner')
    print('shape of left and right merge fs6.0 df {}'.format(fs60_data.shape))

    # rename columns
    fs60_col_renames ={}
    for roi in fs60_data.columns:
        prefix = None
        if roi not in [subject_ID_col,'lh_MeanThickness_thickness','rh_MeanThickness_thickness','lh_temporalpole_thickness','rh_temporalpole_thickness']:
            if roi.split('_',1)[0] == 'lh':
                prefix = 'L'
            elif roi.split('_',1)[0] == 'rh':
                prefix = 'R'
            else:
                print('Unknown prefix for roi {}'.format(roi))
            
            if aparc == 'aparc':
                roi_rename = prefix + '_' + roi.split('_',1)[1].rsplit('_',1)[0]
            elif aparc == 'aparc.Glasseratlas':
                roi_rename = roi.split('_',1)[1].rsplit('_',1)[0]
            else:
                roi_rename = prefix + '_' + roi.split('_',1)[1].rsplit('_',1)[0]

            # Replace & with 'and' and '-' with '_', otherwise it breaks parsing in statsmodels
            roi_rename = roi_rename.replace('&', '_and_')
            roi_rename = roi_rename.replace('-', '_')
            fs60_col_renames[roi] = roi_rename
            
    fs60_data_std = fs60_data.rename(columns=fs60_col_renames).copy()
    
    # Splitting SubjID column to ignore site name
    _, fs60_data_std[subject_ID_col] = fs60_data_std[subject_ID_col].str.split('-', 1).str
    return fs60_data_std
