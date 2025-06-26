# Gabriel-et-al_2025_CircLentiReporter
Scripts used for data analysis and preprocessing as used in the manuscript "tbd" published in "tbd"

# Fiji Macros

##Calculation_illumination_correction.ijm

  OBJECTIVE:
  - calculates an illumination function from a stack of (multicolor) microscopy images, which can be used to correct uneven illumination.
  INPUTS:
  - input image stack should have multiple images of backgroud recordings (e.g. image medium only) recorded with the same settings as the expreimental images
  FUNCTION:
  - for each color,
    - for each each picture:
      - picture is median filteres (radius=5)
      - picture is mean filterd (radius=40)
      - from the filtered(=blurred) image, relative intensity is calculated, maximum is set to 1
    - the average of all relative intensities is calculated by Z-projection
    - this 'correction_function' is stored as a .tif file and can be used for illimunation correction
   
##Preprocessing_illumunation_correction_batch_32bit.ijm

  OBJECTIVE 
  - corrects for uneven illumiation using 'correction_functions'
  - subtracts background
  - (optional) applies binning (2x2) or (4x4) using average
 INPUTS 
  - which channel(s) of original images to process and store in the preprocessed files
  - whether to apply binning (can be 0 = no binning, 2, 4)
  - input folder with .tif, .tiff or .nd2 files to process (file dialog will open)
  - correction_function for each channel to process (file dialog will open)
  FUNCTION
  - converts image to 32-bit
  - corrects the input files illumination by dividing each image by the relative pattern
  - then detects the background level per image as the modal value of a blurred (Gaussion with radius = 50) 16bit image
  - subtracts this value from the image
  - stores the preprocessed stack
  - also stores all background values per stack in a csv files

# Tracking
  - cells were tracked using TrackMate Batcher v1.4.1 plugin of ImageJ 1.54p
  - Segmentation: Stardist, size filter 3µm
  - Tracking: LAP, maximal rnge: 30 µm, no gaps allowed
  - exported spot table

# TrackMatePostGui
  OBJECTIVE
  - tracking is not error free, so TrackMatePostGui is to qualtiy control tracks and filter for minimal length
  - Optimized for U2OS cells, an histone-based tracking marker, and an imaging interval of 1h
  BASIC CONCEPT
  - cells are tracked by a histone based tracking marker, thus signal condenses when cells devide
  - jumps in object size or tracking marker intensity usually point to wrong segmmentation or tracking (or edge effects)
  - however, when cells divide, changes in traking marker or size ARE normal
  - script detects cell divisions as simultatneous/subsequent peaks in tracking marker and shrinkage in size
  - size jumps and tracking marker jumps NOT related to division are FLAGed
  - tracks are kept if number of timepoints between to FLAGs are > minimum length, otherwise filtered out
  - tracks are also filtered out if detected divisions are closer than 15 h (probably not both division events)
  - data at timepoints of division is extrapolated from surrounding time points
  
  INPUTS

==> GUI expects files to be named in a machine readable way. It can combine replica files to datasets if they have the exactly same name and end in replica numbers (e.g. "_01", "_02" and so on). If that does not work, set replica digits to 0 to not combine files into datasets

    • Choose an input Folder (output folder of batcher)
    •	Select the file suffix (“_tm-output.csv” for TM-GUI, “-spots.csv” for batcher data)
    •	Define replica digits(e.g.: “00”)/delimiter(e.g.:”_”
      o	This is expected to be the final number before the file suffix, and has to have the same number of digits for all files, separated from the rest of the file name by the delimiter. All files having the same name except the replica number are combined into one dataset
      o	When input folder is selected and everthings alright with the naming, number of files and datasets are depicted
      o	If anything is wrong, an error text will appear
        - double check/adapt suffix/digits/delimiter pattern
        - check the highlighted file for naming error, rename or remove this file from the folder
        - update by changing forth and back digits number
      o	change digits to 0 if you do want each file to be analysed separately
    	  - also a fallback option if dataset detection fails
    •	define number of channels, and which of them is the tracking channel 
      o	You can name channels here e.g. to have colors displayed on overview plots
      o	Maximum is 4 digits (limit of excel sheet name!)
    •	Define minimum time points for tracks to be kept
    •	Define tracking interval (default is 60 min)
    •	If using very short tracking intervals (<35 min), enabling “Transform Timepoints” may improve accuracy of QC, as settings are optimized for an interval of 60 min. Quality control will then use only timepoints in an interval of close to 60 min to evaluate accurate tracking. 
    •	Advanced settings can also be modified to optimize accuracy, but performance should be evaluated with caution. May be necessary to adapt to other cell lines, tracking marker or imaging interval. As of to date, default advanced settings can only be changed within the python script. 

  OUTPUT
  - one excel file per dataset (or per file if digits is set to 0) with multiple sheets:
    - overview of QC process
    - div_flags: all cell numbers with timepoints of divisions, FLAGs and whether they are approved
    - per color:
      - raw time series of all cells
      - raw time series of approved cells
      - raw time series of approved cells, with extrapolated values at division time points
      - normalized time series of approved cells, with extrapolated values at division time points
  - overview plots from normalized data for each data set
  - a "used_settings.txt" file including all settings and a list of processed files
