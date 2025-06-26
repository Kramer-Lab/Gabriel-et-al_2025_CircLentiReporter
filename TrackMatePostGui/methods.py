import re
import traceback
from typing import Optional
import pandas as pd
import numpy as np
import os
from matplotlib import pyplot as plt
import logging
from logger import logger
from classes import Settings

def analyze_dataset(input_folder:str, dataset_name:str, files:list,
                    settings:Settings,
                    main_output_folder:str, advanced_settings:dict,
                    )->dict:
    logger.info(f"analysing dataset {dataset_name} from {input_folder}")

    min_len = settings.min_len
    tracking_interval = settings.tracking_interval
    size_jump_threshold = advanced_settings["size_jump_threshold"]
    tracking_marker_jump_threshold= advanced_settings["tracking_marker_jump_threshold"]
    tracking_marker_peak_threshold=advanced_settings["tracking_marker_division_peak_threshold"]
    suffix = settings.suffix

    if not settings.digits:
        settings.delimiter = ""

    tracking_marker = settings.get_tracking_marker_name()
    main_channels = [color for color in settings.channel_names.values() if color != tracking_marker]
    channels_to_color = settings.channel_names
   
    subsets = [file.split(suffix)[0][-settings.digits:] for file in files if dataset_name in file]

    output_folder = create_folder(main_output_folder + dataset_name + "/")

    results = {"dataset": dataset_name,
               "error": None,
               "output_folder": output_folder,
               "run_complete": False}

    logger.debug(f"analysing dataset {dataset_name}")

    try:
        # fill input list with subset number and files
        input_file_list = []
        #for a single file in a subset
        if len(subsets)==1 and (not settings.digits):
            input_file_list = [("", subsets[0]+suffix)]
        #for multiple files per subset
        else:
            for subset in subsets:
                input_file_list.append((subset, f'{input_folder}/{dataset_name}{settings.delimiter}{subset}{suffix}'))

        input_tables_cells:dict[str:pd.DataFrame] = {} # will hold raw data_frames per subset
        input_files_used = []

        for subset, file in input_file_list:

            # loading cell data
            if not os.path.exists(file):
                logger.warning(F"file: {file} not found")
                continue
            try:
                logger.debug(f"processing file {file}")
                #read subset csv
                input_table = pd.read_csv(file, low_memory=False).iloc[3:] #first lines are redundant
                input_files_used.append((subset, file))

                #store subset-data in 'input_table_cells'
                input_tables_cells[subset] = input_table.dropna(subset=["TRACK_ID"])

                #add subset name to TRACK_IDs
                input_tables_cells[subset].loc[:, "TRACK_ID"] = (
                    input_tables_cells[subset]["TRACK_ID"].astype(int).astype(
                    str).apply(add_subset_number, args=(subset,)))

            except:
                logger.warning(f'subset {subset} could not be loaded from {input_folder}')
                continue

        #combine DataFrames of all subsets of a dataset into a single DataFrame
        try:
            if len(input_tables_cells.values()) == 1:
                input_data_frame = list(input_tables_cells.values())[0]
            else:
                input_data_frame = pd.concat(input_tables_cells.values())

        except:
            logger.error("Could not load any data set")
            raise ValueError('Could not load any data set')

        time_transformer = 1
        if settings.transform:
            logger.debug(f'tracking intefval: {tracking_interval}')
            if tracking_interval > 35:
                logger.warning("time transformation not used, only valid for tracking intervals < 35 min")
                settings.transform = False
            else:
                time_transformer = round(60 / tracking_interval)
                logger.info(f"time transformation: only using every {time_transformer}. timepoint")



        # Tables with values
        # Extract fluorescence signal timeseries as a dict with color as keys and DataFrame as values
        signals_raw:dict[str:pd.DataFrame] = extract_raw_time_series(input_data_frame, channels_to_color, min_len)

        # Extract object size timeseries per track as a DataFrame
        object_sizes:pd.DataFrame = extract_size_time_series(input_data_frame, min_len).iloc[0::time_transformer]

        # From object size, calculate relative size changes compared to previous time point
        # then mark size jumps over the size_jump_threshold (either up = 1, or down = -1) (division or mis-tracking)
        size_jumps:pd.DataFrame = (object_sizes
                                         .apply(difference_to_prev)
                                         .apply(mark_jumps, args=(size_jump_threshold,), axis=0)
                                         )
        # detect jumps in tracking marker intensity above tracking_marker_jump_threshold (mis-tracking)
        tracking_marker_jumps = (signals_raw[tracking_marker].iloc[0::time_transformer]
                                     .apply(difference_to_prev)
                                     .apply(mark_jumps,args=(tracking_marker_jump_threshold,), axis=0)
                                     )


        def get_peaks(timeseries:pd.Series, threshold:float, n_rolling:int=7)->pd.Series:
            smooth = timeseries.rolling(window=n_rolling, center=True).mean()
            diffs_to_smooth = timeseries-smooth
            mean = diffs_to_smooth.mean()
            std = diffs_to_smooth.std()
            if threshold >= 0:
                peaks = diffs_to_smooth.apply(lambda x: 1 if x > mean + (threshold * std) else 0)
            else:
                peaks = diffs_to_smooth.apply(lambda x: 1 if x < mean + (threshold * std) else 0)
            return peaks

        #detect peaks in tracking marker above tracking_marker_peak_threshold (mis-tracking or division)
        tracking_marker_peaks = signals_raw[tracking_marker].iloc[0::time_transformer].apply(
            get_peaks,
            args=(tracking_marker_peak_threshold,))

        # Define cell divisions: Peak in iRFP signal AND drop subsequent in cell size
        cell_divisions = {}

        for cell in signals_raw[tracking_marker]:
            cell_divisions[cell] = []
            # collect all tracking marker peak times (first tp if there are consecutives)
            peak_times = list(tracking_marker_peaks[cell][tracking_marker_peaks[cell] == 1].index)
            logger.debug(f'trackmarker peak times of cell {cell} are {peak_times}')
            peak_times_single = [time for time in peak_times if time - 1*time_transformer not in peak_times]
            # look up if peak time is parallels or preceeds a decline in size, if yes count as cell division
            for peak_time in peak_times_single:
                if not settings.transform:
                    if -1 in list(size_jumps[cell].loc[peak_time:peak_time + int(round(2/(tracking_interval/60)))]):
                        cell_divisions[cell].append(peak_time)
                else:
                    if -1 in list(
                            size_jumps[cell].loc[peak_time:peak_time + 2*time_transformer]):
                        cell_divisions[cell].append(peak_time)


        # helper function to list surrounding timepoints of a defined interval before and after
        def get_surrounding_timepoints(list_of_tps:list,
                                       rel_start:float,
                                       rel_end:float,
                                       tracking_interval:float,
                                       time_transformer = 1
                                       )->list[int]:
            """
            :param list_of_tps: list[int]
            :param rel_start: float in hours
            :param rel_end: float in hours
            :param tracking_interval: float in minutes
            :return: list[int] a list of timepoints
            """
            if time_transformer == 1:
                rel_start = int(round(rel_start / (tracking_interval / 60)))
                rel_end = int(round(rel_end / (tracking_interval / 60)))

            else:
                rel_start = rel_start * time_transformer
                rel_end = rel_end * time_transformer

            extended_list = []
            for tp in list_of_tps:
                extended_list += list(range(tp + rel_start, tp + rel_end + 1, time_transformer))
            return list(set([x for x in extended_list if x > 0]))

        logger.debug(f'tracking intefval: {tracking_interval}')
        test_surrunding_timepoints = get_surrounding_timepoints([20], 0,2,
                                                                             tracking_interval,
                                                                             time_transformer=time_transformer)
        logger.debug(f"a division at tp 20 spans {test_surrunding_timepoints}")

        # List size jumps that are not connected with divisions. Most cases either mis-tracking or edge-effects
        non_division_size_jumps = {}

        for cell in size_jumps:
            non_division_size_jumps[cell] = []
            #list size jumps times
            size_jump_times = list(size_jumps[cell][size_jumps[cell] != 0].index)
            logger.debug(f'size jumps of cell {cell} are {size_jump_times}')
            #if size jumps do not happen at or within 2 hours after division, list as non-division size jump
            for size_jump_time in size_jump_times:
                if not size_jump_time in get_surrounding_timepoints(cell_divisions[cell], 0,
                                                                    2, tracking_interval,
                                                                    time_transformer=time_transformer):
                    non_division_size_jumps[cell].append(size_jump_time)

        # List tracking marker jumps not related to cell division, most cases mis-tracking
        non_division_tracking_marker_jumps = {}
        for cell in tracking_marker_jumps:
            non_division_tracking_marker_jumps[cell] = []
            # list tracking_marker intensity jumps times
            tracking_marker_jump_times = list(tracking_marker_jumps[cell][tracking_marker_jumps[cell] != 0].index)
            logger.debug(f'trackmarker jumps of cell {cell} are {tracking_marker_jump_times}')
            # if jumps not within 2 hours of division, list as non-division tracking_marker_jump
            for tracking_marker_jump_time in tracking_marker_jump_times:
                if not tracking_marker_jump_time in get_surrounding_timepoints(cell_divisions[cell],-2,
                                                                    2, tracking_interval,
                                                                    time_transformer=time_transformer):
                    non_division_tracking_marker_jumps[cell].append(tracking_marker_jump_time)

        # identify cells with too close devisions (>1 in 15h), probably something went wrong

        def get_close_divisions(divisions:dict[str:list[int]], interval:float)->list[str]:
            cells_with_close_divisions = []
            for cell, div_time_list in divisions.items():
                if len(div_time_list) > 1:
                    for position, div_time in enumerate(div_time_list[:-1]):
                        if (div_time_list[position + 1] - div_time_list[position]) < (15/(interval/60)):

                            cells_with_close_divisions.append(cell)
                            break
            return cells_with_close_divisions

        close_divisions = (get_close_divisions(cell_divisions, interval=tracking_interval))

        #sort out all potential tracking errors:
        ## if track contains potential errors, keep longest error free track if > pre-defined min_len
        ## signals_cleaned only contain error-free time-series
        ## signals_cleaned_rel are devided by mean of time-series

        signals_cleaned = {}
        signals_cleaned_rel = {}

        # for all cells combine non_division_size_jumps and non_division_irfp_jumps to 'flags'
        flags_per_cell = {cell: list(set(non_division_size_jumps[cell]
                                         + non_division_tracking_marker_jumps[cell]))
                          for cell in non_division_size_jumps.keys()}

        # keep only error free long enough time series
        for color_count, (color, raw_signals) in enumerate(signals_raw.items()):
            # for the first iteration/color, filter cells and timeseries using filter_cells methods
            if color_count == 0:
                # remember which color was processed with filter_cells for later reference
                first_color = color
                signals_cleaned[color] = filter_cells(raw_signals,
                                                      flags_per_cell=flags_per_cell,
                                                      close_divisions=close_divisions,
                                                      min_len=min_len)
            # than apply the filtering result to the other colors
            else:
                # select the cells kept in filter_cells
                raw_signals_good_cells = raw_signals[signals_cleaned[first_color].columns]
                # copy the 'na's from first iteration,
                # this crops the timeseries to not contain flags as done by filter cells
                raw_signals_good_cells_cropped = raw_signals_good_cells.mask(signals_cleaned[first_color].isna())
                # safe results
                signals_cleaned[color] = raw_signals_good_cells_cropped
            # calculate relative values nromalized to mean of each time series
            signals_cleaned_rel[color] = signals_cleaned[color] / np.mean(signals_cleaned[color], axis=0)

        #generate list of cells
        all_cells = [cell for cell in signals_raw[tracking_marker]]
        approved_cells = [cell for cell in signals_cleaned[tracking_marker]]

        # smoothen out cell division time points #MISSING: tracking interval...
        signals_smooth_clean_rel, signals_smooth_clean = {}, {}
        for color, raw_signals in signals_cleaned_rel.items():
            signals_smooth_clean_rel[color] = smoothen_out_divisions(signals_cleaned_rel[color], cell_divisions, tracking_interval)
        for color, raw_signals in signals_cleaned.items():
            signals_smooth_clean[color] = smoothen_out_divisions(signals_cleaned[color], cell_divisions, tracking_interval)

        nsubplots = 2 * len(main_channels) + 2

        fig, axs = plt.subplots(1, nsubplots, figsize=(30, 5))
        for i, color in enumerate(main_channels):

            #plot heatmap
            ax = axs[2 * i]
            df = signals_smooth_clean_rel[color].T

            df["tmax"] = df.iloc[:,:].idxmax(axis=1)
            sort = df.sort_values(by="tmax", axis=0).drop("tmax", axis=1)

            ax.imshow(sort, cmap="viridis", interpolation='nearest', vmin=(0.2), vmax=(2.6), aspect="auto")
            ax.set_title(F"{color} Rel. Signals")
            ax.set_ylabel("#cells")
            ax.set_xlabel("[h]")

            ax = axs[2 * i + 1]
            ax.plot(signals_smooth_clean_rel[color].mean(axis=1), c="red", label="mean")
            ax.plot(signals_smooth_clean_rel[color].median(axis=1), c="green", label="median")
            ax.legend()
            ax.set_title(F"{color} normalized")
            ax.set_ylabel("Amplitude")
            ax.set_xlabel("[h]")
            ax.set_ylim([0.3, 2.5])

        axs[nsubplots - 2].plot(signals_smooth_clean_rel[tracking_marker].count(axis=1))
        axs[nsubplots - 2].set_title("Cell Count")
        axs[nsubplots - 2].set_ylabel("# cells")
        axs[nsubplots - 2].set_xlabel("[h]")

        for i, color in enumerate(main_channels):
            axs[nsubplots - 1].boxplot(signals_cleaned[color].mean(), positions=[i + 1, ]),
        axs[nsubplots - 1].set_xticks(list(range(1, len(main_channels) + 1)))
        axs[nsubplots - 1].set_xticklabels(main_channels)
        axs[nsubplots - 1].set_title("Mean Signal")
        axs[nsubplots - 1].set_ylabel("a.u.")
        axs[nsubplots - 1].set_xlim(0.5, 0.5+len(main_channels))

        for ax in fig.get_axes()[:-1]:
            make_ax_circadian(ax, signals_raw[tracking_marker], interval=tracking_interval)
        #plt.show()
        fig.suptitle(F'{dataset_name}')
        fig.savefig(output_folder + f'overview_accepted_cells_{dataset_name}.png', dpi=50)
        fig.savefig(output_folder + f'overview_accepted_cells_{dataset_name}(high_res).png', dpi=300)
        plt.close(fig)

        # Create a Pandas Excel writer using XlsxWriter as the engine.
        writer = pd.ExcelWriter(output_folder + f'post_script_output_{dataset_name}.xlsx')

        # Write each dataframe to a different worksheet.

        overview = [["cells", len(all_cells)],
                    ["approved_cells", len(approved_cells)],
                    ["minimum length", min_len]] + \
                   [[F'mean signal {color}', signals_cleaned[color].mean().mean()] for color in channels_to_color.values()]


        cell_divisions_flags = []
        for cell in signals_raw[tracking_marker]:
            cell_divisions_flags.append({"cell_number": cell,
                                         "divisions": cell_divisions[cell],
                                         "flags": list(set(non_division_size_jumps[cell] +
                                                           non_division_tracking_marker_jumps[cell])),
                                         "approved": cell in approved_cells,
                                         })

        pd.DataFrame(overview).to_excel(writer, sheet_name='overview')
        pd.DataFrame(cell_divisions_flags).to_excel(writer, sheet_name='div_flags')
        for color in channels_to_color.values():
            signals_raw[color].to_excel(writer, sheet_name=F'{color}_raw_all_cells')
            signals_cleaned[color].to_excel(writer, sheet_name=F'{color}_raw_acpt_cells')
            signals_smooth_clean[color].to_excel(writer, sheet_name=F'{color}_raw_acpt_cells_smoothDiv')
            signals_smooth_clean_rel[color].to_excel(writer, sheet_name=F'{color}_norm_acpt_cells_smoothDiv')

        writer.close()

    except Exception:
        results["error"] = traceback.format_exc()
        return results

    results["output_folder"]=output_folder
    results["run_complete"]=True
    results["all_cells"]=len(all_cells)
    results["approved_cells"]= len(approved_cells)
    results["fig_path"]= output_folder + f'overview_accepted_cells_{dataset_name}.png'

    return results

def create_folder(path):
    if not os.path.exists(path):
        os.mkdir(path)
    return path

def filter_cells(dataframe:pd.DataFrame, flags_per_cell:dict, close_divisions:dict, min_len:int)->pd.DataFrame:
    cells_to_drop = []
    #make a copy
    filtered_df = dataframe.copy(deep=True)
    #iterate through cells in flaglist

    for cell, flag_list in flags_per_cell.items():
        #cells with close divisions are added to drop list
        if cell in close_divisions:
            cells_to_drop.append(cell)
            continue
        #if there is no flag keep the cell (nothing to be done)
        elif not flag_list:
            continue

        # get the time series for the cell
        cell_time_series = dataframe[cell].dropna()
        #search for longset interval without flags
        #make list of start time, flags, end time
        start_flag_end = np.array(sorted([int(cell_time_series.index[0]) - 1]
                              + flag_list
                              + [int(cell_time_series.index[-1]) + 1]))
        #calculate length of intervals
        interval_lengths = np.diff(start_flag_end)
        #determine index of longest interval
        idx_longest_interval = np.argmax(interval_lengths)
        #get start and end time of this interval
        start_longest_interval = start_flag_end[idx_longest_interval]
        end_longest_interval = start_flag_end[idx_longest_interval + 1]
        #crop time series to longest interval
        cell_time_series = cell_time_series.loc[start_longest_interval:end_longest_interval]

        #if remaining time series too short than add to drop list
        if cell_time_series.shape[0] < min_len:
            cells_to_drop.append(cell)
        else:
            #keep the cropped time series if long enough
            filtered_df[cell] = cell_time_series


    #drop cells from drop list
    filtered_df = filtered_df.drop(list(set(cells_to_drop)), axis=1)

    return filtered_df

# smoothen out cell division time points
def smoothen_out_divisions(dataset:pd.DataFrame,
                               cell_divisions:dict[str:list[int]],
                               tracking_interval:float
                               )->pd.DataFrame:
    df = dataset.copy(deep=True)
    #how many time points to extrapolate
    width = int(2/(tracking_interval/60))
    if width <2:
        width = 2
    before = (int(width-2)/2)
    after = width-before

    for cell, division_list in cell_divisions.items():
        try:
            for div_t in division_list:
                df.loc[div_t-before:div_t+(after-1), cell] = np.linspace(df[cell].loc[div_t-before-1],
                                                                         df[cell].loc[div_t+after],
                                                                         width+2)[1:-1]
        except:
            continue
    return df


def make_ax_circadian(ax, irfp_signals, interval):
    ax.set_xlabel("[h]")
    data_count = irfp_signals.shape[0]
    max_time = int(data_count*interval/60)
    x_ticks = np.array(range(0,max_time,12), dtype=float)/(interval/60)
    x_tick_labels = list(range(0,max_time,12))

    ax.set_xticks(x_ticks)
    ax.set_xticklabels(x_tick_labels)
    ax.set_xlim(0,data_count)

    ax.grid()


def difference_to_prev(time_series:pd.Series)->pd.Series:
    return time_series.diff()/time_series


def max_min_null(value:float, max_cutoff:float, min_cutoff:Optional[float]=None)->int:
    if not min_cutoff:
        min_cutoff= -1 * max_cutoff
    if value >= max_cutoff:
        return 1
    elif value <=min_cutoff:
        return -1
    else:
        return 0

def mark_jumps(time_series:pd.Series, cutoff:float)->pd.Series:
    return time_series.apply(max_min_null, args =(cutoff,))

def add_subset_number(name:str, subset_nr:str)->str:
    return f'{subset_nr}_{name}'

def df_to_numeric(df:pd.DataFrame)->pd.DataFrame:
    for x in df.columns:
        df[x]=pd.to_numeric(df[x])
    return df

def extract_raw_time_series(input_df:pd.DataFrame,
                            channels_to_color:dict[int:str],
                            min_len:int
                            )->dict[str:pd.DataFrame]:
    signals_raw = {}
    for channel, color in channels_to_color.items():
        #per color, extract dataframe with each track as a column containing fluorescence time series
        signals_raw[color] = (input_df.drop_duplicates(subset=["TRACK_ID", "FRAME"])
                              .pivot(index="FRAME",
                                                columns="TRACK_ID",
                                                    values=f'MEAN_INTENSITY_CH{channel}' )
                              .reset_index().reset_index(drop=True))

        signals_raw[color].FRAME = pd.to_numeric(signals_raw[color].FRAME)
        signals_raw[color]= signals_raw[color].sort_values(by="FRAME").set_index("FRAME", drop=True)
        #drop time series shorter than limit
        signals_raw[color]= signals_raw[color].loc[:, signals_raw[color].count(axis=0)>min_len]
        signals_raw[color] = df_to_numeric(signals_raw[color])
    return signals_raw


def extract_size_time_series(input_df:pd.DataFrame, min_len:int)->pd.DataFrame:
    # extract dataframe with each track as a column containing size time series
    sizes = input_df.drop_duplicates(subset=["TRACK_ID", "FRAME"]).pivot(index="FRAME",
                                                columns="TRACK_ID",
                                                    values=f'AREA' ).reset_index().reset_index(drop=True)

    sizes.FRAME = pd.to_numeric(sizes.FRAME)
    sizes =sizes.sort_values(by="FRAME").set_index("FRAME")
    # drop time series shorter than limit
    sizes = sizes.loc[:, sizes.count(axis=0)>min_len]
    return df_to_numeric(sizes)