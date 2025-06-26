//VERSIONINFO: Last Changes on 10.4.25

#@ int use_channel_1
#@ int use_channel_2
#@ int use_channel_3
#@ int use_channel_4
#@ int use_channel_5
#@ int use_channel_6
#@ int use_channel_7

#@ int binning


// Set the input and output directories
inputDir = getDirectory("Choose a Directory with input files");
outputDir = getDirectory("Choose a Directory to store output files");
backgroundDir = outputDir + "Backgrounds/"
File.makeDirectory(backgroundDir);


// Get a list of all files in the input directory
list = getFileList(inputDir);
//count image files
totalFileCount = 0;
for(i=0; i<list.length; i++)
{
	path = inputDir + list[i];
	if (File.isFile(path) && (endsWith(path, ".tif") || endsWith(path, ".nd2") || endsWith(path, ".tiff")))
		{totalFileCount++;	};	
}

//collect which channel to use
use_channels = newArray(use_channel_1, use_channel_2, use_channel_3,use_channel_4, use_channel_5, use_channel_6, use_channel_7);
correction_files = newArray(7);

setBatchMode("hide");

// ask for correction files
for(i=0; i<7; i++)
{
	if(use_channels[i] == 1)
	{
		correction_files[i] = File.openDialog("Choose Correction File " + i+1);
	}
};

// count channels
channels = use_channel_1 + use_channel_2 + use_channel_3 + use_channel_4 + use_channel_5 + use_channel_6 + use_channel_7
corrected_stacks = newArray(channels);

//get timestamp for settings file
getDateAndTime(year, month, dayOfWeek, dayOfMonth, hour, minute, second, msec);
if(dayOfMonth < 10){dayOfMonth = "0" + dayOfMonth;}
if(month < 10){month = "0" + month;}
if(hour < 10){hour = "0" + hour;}
if(minute < 10){minute = "0" + minute;}
if(second < 10){second = "0" + second;}
TimeString = ""+ year + "-" + month + "-" + dayOfMonth + "_" + hour + "-" + minute + "-" + second+ "";

//create setting file
settingsFile = outputDir + "settings_preprocessing(" + TimeString + ").txt"; // filename
SettingsString = "Processing started at: " + TimeString + "\n" + //collect all settings
                "Use Channel1: " + use_channel_1 + "\n" +
                "Use Channel2: " + use_channel_2 + "\n" +
                "Use Channel3: " + use_channel_3 + "\n" +
                "Use Channel4: " + use_channel_4 + "\n" +
                "Use Channel5: " + use_channel_5 + "\n" +
                "Use Channel6: " + use_channel_6 + "\n" +
                "Use Channel7: " + use_channel_7 + "\n" +
                "Binning: " + binning + "\n\n";

CorrFileString = ""; // collect correction files' names to write in file
for(i=0; i<7; i++){CorrFileString = CorrFileString + "CorrectionFile"+ (i+1)  +": "+ correction_files[i]+ "\n";};

//write settings in file
File.saveString(SettingsString + CorrFileString + "\nFiles PreProcessed:\n"   , settingsFile);

// START OF MAIN LOOP

//generate Progress Window
run("Text Window...", "name=[Progress info] width=90 height=1");

// Loop through each file in the directory
processingImageNumber = 0; //count of image that is processed
for (processing_file_count = 0; processing_file_count < list.length; processing_file_count++) 
{
    
    
    // Get the current file name
    fileName = list[processing_file_count];
    path = inputDir + fileName;
    // Check if the file is a valid image file (you can modify this as needed)
    if (File.isFile(path) && (endsWith(path, ".tif") || endsWith(path, ".nd2") || endsWith(path, ".tiff"))) 
	{
        //update Progress Window
        processingImageNumber++;
        print("[Progress info]", "\\Update:Finished Processing: " + processing_file_count+" of " + totalFileCount + " images");
        
        // Open the file using Bio-Formats
        run("Bio-Formats Importer", "open=[" + inputDir + fileName + "] color_mode=Default view=Hyperstack stack_order=XYCZT");
        input_stack = getImageID();

		// create background file
		bgFilePath = backgroundDir + fileName + ".csv";
		
		// nchannels = number of channels of stack
		getDimensions(width, height, nchannels, slices, frames);
		

		for (i=0; i<7; i++)
		{
			if(use_channels[i] ==1)
			{
		        //choose channel
						
		        selectImage(input_stack);
		        current_channel = i+1;
		        run("Duplicate...", "duplicate channels=current_channel");
				
				//count slices/timepoints
		        slices = nSlices;
		        current_channel_stack = getImageID();
		

            //correct stack usingn correction file [i]
                //open correction file
                open(correction_files[i]);
                current_correction_file = getImageID();
                max_correction_file = getValue("Max");

                //devide by correction file
                imageCalculator("Divide 32-bit create stack", current_channel_stack, current_correction_file);
                corrected_stack = getImageID();
                selectImage(current_correction_file);
                close();
                selectImage(current_channel_stack);
                close();
                selectImage(corrected_stack);
                //multiply by max of correction file
                run("Multiply...", "value=max_correction_file stack");
                setMinAndMax(0, 65535);
	       
	       //background subtraction
		        //duplicate stack
		        selectImage(corrected_stack);
		        run("Duplicate...", "duplicate");
		        setMinAndMax(0, 65535);
		        run("16-bit"); //more stable modal value
		        stack_for_BG = getImageID();
		
		        //apply gaussion blur to duplicate
		        run("Gaussian Blur...", "sigma=2 stack");
		
		        //measure modal of blurred stack and store in BG list
		        BG_current_channel = newArray(nSlices); // this one is used for calculation later
		        channelBG = "BGchannel"+(i+1)+","; //this one is for documentation in BG file
		
		        for(j=1; j<nSlices+1; j++)
		        {
		            Stack.setFrame(j);
		            //exclude saturated pixels
		            setThreshold(0, 60000);
		            // Create a selection from the threshold
		            run("Create Selection");
		            //add modal to background lists
		            BG_current_channel[j-1] = getValue("Mode");
		            channelBG = channelBG + getValue("Mode") + ","; 
		        }
				//close blurred stack
		        close();
		
		        //for each image
		        selectImage(corrected_stack);
		        for(j=1; j<nSlices+1; j++)
		        {
		            //subtract modal
		            Stack.setFrame(j);
		            bg_for_slice = BG_current_channel[j-1];
		            run("Subtract...", "value=bg_for_slice slice");
		        }
		        rename("color"+i);
		        //add to list of corrected stacks
		        corrected_stacks[i] = getTitle();
		        
		        //generate background file on first channel iteration
		        if (File.isFile(bgFilePath) == false)
		        {
		        	tpString = "Channel,";
		        	//add list of timepoints as first row		        	
		        	for(j=0; j<nSlices; j++)
		        		{tpString = tpString + j + ",";};
		        	tpString = tpString + "\n"; 
		        	File.saveString(tpString, bgFilePath);	
		        }
		        //write channel backgrounds to background file
		        File.append(channelBG, bgFilePath);		        
		    };		
		};
		
		// combine corrected stacks of all channels into new hyperstack
		if(channels >1)
		{
			//collect names and combine into one string
			merge_string = "";
			for (i=0; i<7; i++)
			{
				if(use_channels[i] ==1)
					{
					merge_string = merge_string + "c" + i+1 + "=" + corrected_stacks[i] + " ";
					};
			};
			//merge channels using string
			
			run("Merge Channels...", merge_string + "create");
			Stack.setDisplayMode("color");
		
		}
		
		//bin results if binning is selected
		if(binning == 2)
		{
		    run("Bin...", "x=2 y=2 z=1 bin=Average");
		}
		
		if(binning == 4)
		
		{
		    run("Bin...", "x=4 y=4 z=1 bin=Average");
		}
		
		//safe result file
		saveAs("Tiff", outputDir + fileName);
		//add Filename to settings file		
		File.append("" + fileName, settingsFile)

		close("*");
		run("Collect Garbage");
		
    };
};
		
setBatchMode("show");
showMessage("Finished", "processed all " +totalFileCount+ " images and stored at "+ outputDir);		