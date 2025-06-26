import logging
import argparse
import os.path
import time, datetime
from idlelib.help import HelpWindow

from PyQt5.QtWidgets import (QApplication,

                             QLineEdit,
                             QMainWindow,
                             QSpinBox,
                             QWidget, QDialog,
                             QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog, QScrollArea, QProgressBar, QFrame,
                             QMessageBox, QCheckBox, QButtonGroup, QGroupBox, QRadioButton
                             )
import traceback, sys
from methods import *
from classes import *
from logger import logger


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        #variable to break execution
        self.keep_running = True

        #multithreading
        self.threadpool = QThreadPool()

        # define default variables
        self.selected_folder = "Choose Input Folder"
        self.number_channels=3
        self.file_list = []
        self.dataset_list=[]
        self.input_file_suffix = ""
        self.advanced_settings={
            "size_jump_threshold"  : 0.2,
            "tracking_marker_jump_threshold" : 0.18,
            "tracking_marker_division_peak_threshold": 1.5,
            }

    # set main layout
        self.setWindowTitle("TrackMate PostProcessor")
        self.setMinimumSize(QSize(500,500))
        layout = QVBoxLayout()

    # help window button
        layout.addWidget(self.create_push_button("HELP?", self.open_help_window))

    # choose input file
        layout.addLayout(self.create_layout_folder_selection())

    # suffix selection
        layout.addWidget(self.create_suffixGroupBox())

    # file suffix + separator
        layout.addLayout(self.create_layout_file_selection())

    #number of channels to use
        layout.addLayout(self.create_layout_channel_selection())

    # channel names
        layout.addLayout(self.create_layout_channel_names())

    #minimum tracking length
        layout.addLayout(self.create_layout_minlen_and_interval())

    # transform tps for quality control
        self.transform_checkbox = QCheckBox("Transform timepoints")
        layout.addWidget(self.transform_checkbox)

    # advanced settings button
        layout.addWidget(self.create_push_button('Advanced settings', self.open_advanced_settings))

    # execute & Stop button
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.create_push_button("Start", self.execute))
        button_layout.addWidget(self.create_push_button("Stop", self.stop_execution))
        layout.addLayout(button_layout)

    #progress_bar
        layout.addWidget(self.create_progress_bar_widget())

    # place layout into main window
        widget = QWidget()
        widget.setLayout(layout)
        self.setCentralWidget(widget)

    def open_help_window(self):
        try:
            with open(os.path.join(BASEDIR, "help_dialog.txt"), "r") as help_text_file:
                text = help_text_file.read()
            self.help_window = HelpWindow(text)
            self.help_window.show()
        except:
            traceback.print_exc()

    def open_advanced_settings(self):
        try:
            self.advanced_settings_window = AdvancedSettingsWindow(self)
            self.advanced_settings_window.show()
        except:
            traceback.print_exc()

    def change_advanced_settings(self, settings_to_update:dict):
        self.advanced_settings.update(settings_to_update)

    def stop_execution(self):
        self.keep_running = False

    def create_layout_folder_selection(self):
        layout_folder_selection = QHBoxLayout()
        self.selected_folder_label = QLabel(F'Input Folder: {self.selected_folder}')
        choose_folder_button = QPushButton("Choose Input Folder")
        choose_folder_button.clicked.connect(self.choose_folder_button_clicked)
        choose_folder_button.setFixedSize(QSize(140, 30))
        layout_folder_selection.addWidget(self.selected_folder_label)
        layout_folder_selection.addWidget(choose_folder_button)
        return layout_folder_selection

    def choose_folder_button_clicked(self):
        new_folder = QFileDialog.getExistingDirectory(self, "Select Input Directory")
        if not new_folder:
            return
        else:
            self.selected_folder = new_folder
            folder_label = ""
            for i in range(0,181,50):
                try:
                    folder_label += self.selected_folder[i:i+50]+"\n"
                except:
                    folder_label += self.selected_folder[i:]
                    break
            self.selected_folder_label.setText(F'Main Folder: {folder_label}')

            self.search_input_folder()

    def create_suffixGroupBox(self):

        suffixGroupBox = QGroupBox("Select File Suffix")
        self.use_tm_output_radiobutton = QRadioButton("_tm-output.csv")
        self.use_spot_radiobutton = QRadioButton("-spots.csv")
        self.use_other_suffix_radiobutton = QRadioButton("other:")
        self.input_file_suffix_entry = QLineEdit("")
        self.input_file_suffix_entry.textChanged.connect(self.other_suffix_entry_changed)
        self.input_file_suffix_entry.textChanged.connect(self.search_input_folder)

        self.use_tm_output_radiobutton.toggled.connect(self.suffix_button_toggled)
        self.use_spot_radiobutton.toggled.connect(self.suffix_button_toggled)
        self.use_other_suffix_radiobutton.toggled.connect(self.suffix_button_toggled)
        self.use_spot_radiobutton.setChecked(True)

        suffix_layout = QHBoxLayout()
        suffix_layout.addWidget(self.use_tm_output_radiobutton)
        suffix_layout.addWidget(self.use_spot_radiobutton)
        suffix_layout.addWidget(self.use_other_suffix_radiobutton)
        suffix_layout.addWidget(self.input_file_suffix_entry)
        suffixGroupBox.setLayout(suffix_layout)
        suffixGroupBox.setFlat(True)
        return suffixGroupBox

    def suffix_button_toggled(self):
        for button in (self.use_tm_output_radiobutton, self.use_spot_radiobutton):
            if button.isChecked():
                self.input_file_suffix = button.text()
                #self.input_file_suffix_entry.setText(button.text())
        if self.use_other_suffix_radiobutton.isChecked():
            self.input_file_suffix = self.input_file_suffix_entry.text()
        logger.debug(f"suffix {self.input_file_suffix}")
        self.search_input_folder()


    def other_suffix_entry_changed(self):
        self.use_other_suffix_radiobutton.setChecked(True)
        self.suffix_button_toggled()


    def search_input_folder(self):

        def get_datasets_from_file_list(file_list:list, separator:str, digits:int, suffix:str)->list[str]:
            if not digits:
                #each file is an individual dataset
                return file_list
            else:
                #look for datasets (groups of files with same name pattern)
                file_list = [file.split(suffix)[0] for file in file_list]

                #check for number of digits
                try:
                    for file in file_list:
                        int(file[-int(digits):])
                except ValueError:
                    raise ValueError(f'problem with file {file}\n, wrong amount of digits ?')
                file_list = [file[:-int(digits)] for file in file_list]

                #check for separator
                if separator:
                    for file in file_list:
                        if not file.endswith(separator):
                            raise ValueError(f'problem with file {file}\n separator not found')
                    file_list = [separator.join(file.split(separator)[:-1]) for file in file_list]
                return list(set(file_list))
        #
        if not os.path.exists(self.selected_folder):
            return
        #list search subfolders
        datasets = []
        files = [file for file in os.listdir(self.selected_folder) if os.path.isfile(self.selected_folder +"/" + file)]
        files = [file for file in files if file.endswith(self.input_file_suffix)]
        if files:
            try:
                datasets = get_datasets_from_file_list(file_list=files,
                                                       separator=self.subset_separator,
                                                       digits=self.subset_digits,
                                                       suffix = self.input_file_suffix)
                new_dataset_text = F'found {len(files)} files in {len(datasets)} datasets'
            except Exception as exp:
                new_dataset_text = F"no datasets found in folder, \n{exp}"


        else:
            new_dataset_text ="no datasets found in folder,\n check Input Folder and suffix"
        self.label_datasets_and_files.setText(new_dataset_text)

        self.file_list = files
        self.dataset_list = datasets

    def create_layout_file_selection(self):

        layout_file_selection = QVBoxLayout()

        label_specify = QLabel("Specify how replicates are labeled")
        label_specify.setAlignment(Qt.AlignHCenter | Qt.AlignBottom)
        layout_file_selection.addWidget(label_specify)

        replicate_number_layout = QHBoxLayout()
        replicate_digits_label = QLabel("digits")
        replicate_digits = QSpinBox()
        replicate_digits.setMinimum(0)
        replicate_digits.setValue(2)
        separator_label = QLabel("delimiter")
        separator_input = QLineEdit("_")
        self.subset_separator = separator_input.text()
        self.subset_digits = replicate_digits.value()
        self.replica_format = self.get_replica_format()
        self.replica_format_label = QLabel(self.replica_format)
        replicate_digits.valueChanged.connect(self.change_digits)
        separator_input.textChanged.connect(self.change_seperator)
        replicate_number_layout.addWidget(replicate_digits_label)
        replicate_number_layout.addWidget(replicate_digits)
        replicate_number_layout.addWidget(separator_label)
        replicate_number_layout.addWidget(separator_input)
        replicate_number_layout.addWidget(self.replica_format_label)
        layout_file_selection.addLayout(replicate_number_layout)

        # datasets and files
        self.label_datasets_and_files = QLabel("")
        self.label_datasets_and_files.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        layout_file_selection.addWidget(self.label_datasets_and_files)
        return layout_file_selection



    def change_seperator(self,new_sep:str):
        self.subset_separator = new_sep
        self.replica_format_label.setText(self.get_replica_format())
        self.search_input_folder()

    def change_digits(self, new_number_digits:str):
        self.subset_digits = new_number_digits
        self.replica_format_label.setText(self.get_replica_format())
        self.search_input_folder()

    def get_replica_format(self)->str:
        return F'{self.subset_separator}{"0"*self.subset_digits}'


    def create_layout_channel_selection(self):
        layout_channel_selection = QHBoxLayout()

        #select number of channels
        spinbox_channel_selection = QSpinBox()
        spinbox_channel_selection.setMinimum(1)
        spinbox_channel_selection.setMaximum(7)
        spinbox_channel_selection.setValue(self.number_channels)
        select_number_channel_label = QLabel("# Channels")
        spinbox_channel_selection.valueChanged.connect(self.number_channel_changed)
        layout_channel_selection.addWidget(select_number_channel_label)
        layout_channel_selection.addWidget(spinbox_channel_selection)

        # select tracking channel
        self.spinbox_tracking_channel_selection = QSpinBox()
        self.spinbox_tracking_channel_selection.setMinimum(1)
        self.spinbox_tracking_channel_selection.setMaximum(self.number_channels)
        self.spinbox_tracking_channel_selection.setValue(self.number_channels)
        label_tracking_channel_selection = QLabel("Tracking Channel")
        # spinbox_channel_selection.valueChanged.connect(self.number_channel_changed)
        layout_channel_selection.addWidget(label_tracking_channel_selection)
        layout_channel_selection.addWidget(self.spinbox_tracking_channel_selection)
        return layout_channel_selection

    def number_channel_changed(self,new_value:int):
        self.number_channels=new_value
        self.spinbox_tracking_channel_selection.setMaximum(self.number_channels)

    def create_layout_channel_names(self):
        layout_channel_names = QVBoxLayout()
        self.channel_names = {
            1: QLineEdit("CH1"),
            2: QLineEdit("CH2"),
            3: QLineEdit("CH3"),
            4: QLineEdit("CH4"),
            5: QLineEdit("CH5"),
            6: QLineEdit("CH6"),
            7: QLineEdit("CH7"),
        }
        for i, line_edit in self.channel_names.items():
            channel_layout = QHBoxLayout()
            channel_label = QLabel(F"Channel {i}")
            channel_layout.addWidget(channel_label)
            channel_layout.addWidget(line_edit)
            layout_channel_names.addLayout(channel_layout)

        return layout_channel_names

    def create_layout_minlen_and_interval(self):
        layout_minlen_and_interval = QHBoxLayout()
        self.spinbox_min_len = QSpinBox()
        self.spinbox_min_len.setMinimum(1)
        self.spinbox_min_len.setMaximum(999)
        self.spinbox_min_len.setValue(48)
        min_len_label = QLabel("Minimum timepoints per track")

        layout_minlen_and_interval.addWidget(min_len_label)
        layout_minlen_and_interval.addWidget(self.spinbox_min_len)

        self.interval_label = QLabel("Tracking interval (min)")
        self.input_interval = QLineEdit("60.0")
        layout_minlen_and_interval.addWidget(self.interval_label)
        layout_minlen_and_interval.addWidget(self.input_interval)

        return layout_minlen_and_interval

    def create_push_button(self, label, button_func):
        button = QPushButton(label)
        button.clicked.connect(button_func)
        return button

    def create_progress_bar_widget(self):
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        return self.progress_bar

    def check_inputs(self):
        if not self.dataset_list:
            raise FileNotFoundError("Found no Dataset to Process")
        try:
            float(self.input_interval.text())
        except:
            raise ValueError("Please provide valid Tracking Interval")

    def execute(self):
        self.keep_running = True
        self.errors = 0
        self.error_report = ""

        try:
            self.check_inputs()
        except Exception as e:
            self.show_error(str(e))
            return

        self.progress_bar.setValue(1)
        self.progress_window = ProgressWindow()
        self.progress_window.scroll_label.set_text("Started Processing...")
        self.progress_window.show()
        worker = Worker(self.run_main)  # Any other args, kwargs are passed to the run function
        worker.signals.progress.connect(self.progress_fn)
        worker.signals.result.connect(self.result_fn)

        # Execute
        self.threadpool.start(worker)

    def progress_fn(self, n:int):

        self.progress_window.progress_bar.setValue(int(100*n/len(self.dataset_list)))
        self.progress_bar.setValue(int(100*n/len(self.dataset_list)))

    def result_fn(self, results:dict):
        result_text = F'\nprocessed {results["dataset"]}\n'
        if not results["run_complete"]:
            result_text += F'  ERROR WHILE ANALYZING DATASET\n'
            logger.error(F'ERROR WHILE ANALYZING DATASET {results["dataset"]}:')
            self.errors += 1
            if results["error"]:
                result_text += F'{results["error"]}\n'
                self.error_report += F'\n{results["error"]}\n'
                logger.error(F'{results["error"]}')
            else:
                result_text += "UNKNOWN ERROR\n"
                logger.error("UNKNOWN ERROR")
        else:
            result_text+= F'  approved_cells: {results["approved_cells"]}/{results["all_cells"]}\n'

        self.progress_window.scroll_label.add_text(result_text)
        logger.info(result_text.replace('\n', ' '))

        if results["run_complete"]:
            self.progress_window.set_fig(results["fig_path"])

    def write_settings_file(self, settings, output_folder:str):
        settings_file_path = os.path.join(output_folder, "used_settings.txt")
        with open(settings_file_path, "w") as used_settings_file:
            settings_text = (
                f'input folder: {self.selected_folder}\n'
                f'number of channels: {settings.number_channels}\n'
                f'tracking channel: {settings.tracking_channel}')
            for n in range(1,settings.number_channels+1):
                settings_text += f"Name Channel {n}: {settings.channel_names[n]}\n"
            settings_text += (
                f'minimum time points: {settings.min_len}\n'
                f'tracking interval: {settings.tracking_interval}\n'
                f'number of digits: {settings.digits}\n'
                f'delimiter: {settings.delimiter}\n'
                f'transform timepoints: {settings.transform}'
                f'file_suffix: {settings.suffix}')
            for setting_name, value in self.advanced_settings.items():
                settings_text += f"{setting_name}: {value}\n"
            settings_text += "\nDATASETS:\n"
            for dataset in self.dataset_list:
                settings_text+=f'  {dataset}\n'

            settings_text += "\nFILES:\n"
            for file in self.file_list:
                settings_text += f'  {file}\n'

            used_settings_file.writelines(settings_text)
            logger.info(f'settings stored at {settings_file_path}')

    def read_settings(self)->Settings:
        settings_dict=\
            {
                "min_len" : self.spinbox_min_len.value(),
                "tracking_interval" : float(self.input_interval.text()),
                "number_channels" : self.number_channels,
                "channel_names" : {number: self.channel_names[number].text() for number in
                                     list(range(1, self.number_channels + 1))},
                "tracking_channel": self.spinbox_tracking_channel_selection.value(),
                "digits": self.subset_digits,
                "delimiter": self.subset_separator,
                "transform": self.transform_checkbox.isChecked(),
                "suffix": self.input_file_suffix

            }
        settings = Settings(**settings_dict)
        return settings


    def run_main(self, progress_callback, result_callback):
        settings = self.read_settings()
        datasets = self.dataset_list
        files = [self.selected_folder + "/" + file for file in self.file_list]

        now = datetime.datetime.now()
        main_output_folder = create_folder(self.selected_folder + "/" + f"grouped_results(post_script_output_"
                                                                        f"{now:%y-%m-%d_%H-%M})/")

        self.write_settings_file(settings, main_output_folder)

        logger.info(f"Start processing {len(files)} files from {len(datasets)} datasets")
        logger.info(f"data will be stored at {main_output_folder}")
        logger.info(f"Settings are: {settings}")

        for i, dataset in enumerate(sorted(datasets[:])):
            # analyze dataset
            if not self.keep_running:

                time.sleep(3)
                self.progress_window.scroll_label.add_text("\nProcessing Stopped!".upper())
                logger.info("process aborted manually")

                return
            results = analyze_dataset(input_folder=self.selected_folder,
                            dataset_name=dataset,
                            files=files,
                            settings = settings,
                            main_output_folder=main_output_folder,
                            advanced_settings = self.advanced_settings,

                          )
            progress_callback.emit(int(i+1))
            result_callback.emit(results)
        time.sleep(2)

        finish_text = F"\nProcessing Finished\n {self.errors} errors occurred!"
        self.progress_window.scroll_label.add_text(finish_text)
        logger.info(finish_text.replace('\n', ' '))

        if self.error_report:
            self.progress_window.scroll_label.add_text(F"Errors:\n {self.error_report}")
            logger.error(F"Errors: {self.error_report}")

    def show_error(self, text:str):
        msg = QMessageBox(parent=self)
        msg.setIcon(QMessageBox.Critical)
        msg.setText("Error")
        msg.setInformativeText(text)
        msg.setWindowTitle("Error")
        msg.exec_()

parser = argparse.ArgumentParser()
parser.add_argument("--logger", type=str, choices= ["info", "debug"],
                    default="info", help="Logging Mode")
args = parser.parse_args()


if args.logger=="debug":
    logger.setLevel(logging.DEBUG)
else:
    logger.setLevel(logging.INFO)

BASEDIR = os.path.dirname(os.path.abspath(__file__))

app = QApplication(sys.argv)
try:
    window = MainWindow()
    window.show()
    app.exec()
except Exception as err:
    traceback.print_exc()
    raise Exception from err