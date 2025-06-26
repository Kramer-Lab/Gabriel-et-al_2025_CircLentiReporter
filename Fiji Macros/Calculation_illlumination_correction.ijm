if (nImages == 0) {
    // Prompt user to select an image file
    
	openPath = File.openDialog("Select a Stack to Caclulate Correction Function");
    // If user cancels dialog, abort macro

    // Open the selected image
    open(openPath);
    dir = File.getDirectory(openPath);
} else {
    origName = getTitle();
    message = "Current image:\n \n     " + origName + "\n \nwill be used for calculation.\n \n             Continue?";    
    showMessageWithCancel("Calculate Correction from Open Image",message);
    
    dir = getDirectory("Choose a Directory to store output files");
    
}

// Iterate through each slice in the stack

imid = getImageID();

origName = getTitle();
dot = lastIndexOf(origName, ".");
if (dot != -1) {
    baseName = substring(origName, 0, dot);
} else {
    baseName = origName;
}
dir = getDirectory("Choose a Directory to store output files");


getDimensions(width, height, channels, slices, frames);
// iterate through the different channels
for (c = 1; c <= channels; c++) {
	
	selectImage(imid);
	run("Duplicate...", "duplicate channels="+c);
	dup_stack = getImageID();
	run("32-bit");
	for (i = 1; i <= nSlices; i++) 
	{
	    // Select the current slice
	    setSlice(i);
	    run("Median...", "radius=5");
	    run("Mean...", "radius=40");
	    // Measure the maximum pixel value in the current slice
	    getStatistics(area, mean, min, max, std, histogram);
	    maxVal = max;
	    run("Divide...", "value=" + maxVal + " slice");
	    
	}
	
	run("Z Project...", "projection=[Average Intensity]");
	savePath = dir +baseName + "_illumination-correction-function_CH" + c + ".tif";
	selectImage(dup_stack);
	close();
    saveAs("Tiff", savePath);
}
showMessage("Completed", "Created Correction function for " +channels+ " channels and stored at \n \n"+ dir);