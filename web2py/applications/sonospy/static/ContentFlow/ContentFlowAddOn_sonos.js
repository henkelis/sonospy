/*  ContentFlowAddOn_DEFAULT, version 1.0.2 
 *  (c) 2008 - 2010 Sebastian Kutsch
 *  <http://www.jacksasylum.eu/ContentFlow/>
 *
 *  This file is distributed under the terms of the MIT license.
 *  (see http://www.jacksasylum.eu/ContentFlow/LICENSE)
 */

/*
 * This is an example file of an AddOn file and will not be used by ContentFlow.
 * All values are the default values of ContentFlow.
 *
 * To create a new AddOn follow this guideline:
 *              (replace ADDONNAME by the name of your AddOn)
 *
 * 1. rename this file to ContentFlowAddOn_ADDONNAME.js
 * 2. Change the string 'DEFAULT' in the 'new ContentFlowAddOn' line to 'ADDONNAME'
 * 3. Make the changes you like/need
 * 4. Remove all settings you do not need (or comment out for testing).
 * 5. Add 'ADDONNAME' to the load attribute of the ContentFlow script tag in your web page
 * 6. Reload your page :-)
 *
 */
new ContentFlowAddOn ('sonos', {

    /* 
     * AddOn configuration object, defining the default configuration values.
     */

    conf: {

        albumFontHeight: 12,
        albumGapHeight: 2,
        leftGapWidth: 2,
        albumFont: '',
        albumX: -1,
        albumY: 2,
        artistX: -1,
        artistY: -1

    },

    /* 
     * This function will be executed on creation of this object (on load of this file).
     * It's mostly intended to automatically add additional stylesheets and javascripts.
     *
     * Object helper methods and parameters:
     * scriptpath:          basepath of this AddOn (without the filename)
     * addScript(path):     adds a javascript-script tag to the head with the src set to 'path'
     *                      i.e. this.addScript(scriptpath+"MyScript.js") .
     *
     * addStylesheet(path): adds a css-stylesheet-link tag to the head with href set to
     *                      'path' i.e. this.addStylesheet(scriptpath+"MyStylesheet.css") .
     *                      If path is omittet it defaults to :
     *                      scriptpath+'ContentFlowAddOn_ADDONNAME.css'.
     *
     */
    init: function() {

        this.conf.albumFont = this.conf.albumFontHeight + 'px sans-serif';
        this.conf.albumX = this.conf.leftGapWidth;
        this.conf.artistX = this.conf.leftGapWidth;
        this.conf.artistY = this.conf.albumY + this.conf.albumFontHeight + this.conf.albumGapHeight;

        // this.addScript();
        // this.addStylesheet();
        
    },

    /* 
     * This method will be executed for each ContentFlow on the page after the
     * HTML document is loaded (when the whole DOM exists). You can use it to
     * add elements automatically to the flow.
     *
     * flow:                the DOM object of the ContentFlow
     * flow.Flow:           the DOM object of the 'flow' element
     * flow.Scrollbar:      the DOM object of the 'scrollbar' element
     * flow.Slider:         the DOM object of the 'slider' element
     * flow.globalCaption:  the DOM object of the 'globalCaption' element
     *
     * You can access also all public methods of the flow by 'flow.METHOD' (see documentation).
     */
    onloadInit: function (flow) {
    },

    /* 
     * This method will be executed _after_ the initialization of each ContentFlow.
     */    
    afterContentFlowInit: function (flow) {

        // create array to hold images for reverse side
        flow.itemsback = new Array();
        
        flow.currentIndex = null;

/*
        // load default reverse image
        defaultbackimage = new Image();
        defaultbackimage.onload = function(){
            defaultbackimage.width = 300;
            defaultbackimage.height = 300;

            // TODO: fix for IE
            
            // write default image to first item context and save it as context data, then restore image
            var item = flow.items[0];
            var context = item.content.getContext("2d");
            
            width = item.content.width;
            height = item.content.height;
            
            tempImageData = context.getImageData(0, 0, width, height);
            item.content.width = width;  // seems we have to re-set this for drawImage to work properly
            item.content.height = height;    // and this
            context.drawImage(defaultbackimage, 0, 0, 300, 300);
            flow.defaultBackImageData = context.getImageData(0,0,300,300);
            context.putImageData(tempImageData, 0, 0);
        }
        defaultbackimage.src = '/sonospy/static/pw.png';                       
*/

    },

    /*
     * ContentFlow configuration.
     * Will overwrite the default configuration (or configuration of previously loaded AddOns).
     * For a detailed explanation of each value take a look at the documentation.
     */
	ContentFlowConf: {
        loadingTimeout: 30000,          // milliseconds
        activeElement: 'content',       // item or content

//        maxItemHeight: 0,               // 0 == auto, >0 max item height in px
        maxItemHeight: 300,     // reflections don't work without this for hacked load post dom load
        scaleFactor: 1.0,               // overall scale factor of content
        scaleFactorLandscape: 1.33,     // scale factor of landscape images ('max' := height= maxItemHeight)
        scaleFactorPortrait: 1.0,       // scale factor of portraoit and square images ('max' := width = item width)
        fixItemSize: false,             // don't scale item size to fit image, crop image if bigger than item
        relativeItemPosition: "top center", // align top/above, bottom/below, left, right, center of position coordinate

        circularFlow: true,             // should the flow wrap around at begging and end?
        verticalFlow: false,            // turn ContentFlow 90 degree counterclockwise
//        visibleItems: -1,               // how man item are visible on each side (-1 := auto)
        visibleItems: 4,
        endOpacity: 1,                  // opacity of last visible item on both sides
//        startItem:  "center",           // which item should be shown on startup?
        startItem:  "first",
        scrollInFrom: "pre",            // from where should be scrolled in?

        flowSpeedFactor: 1.0,           // how fast should it scroll?
        flowDragFriction: 1.0,          // how hard should it be be drag the floe (0 := no dragging)
        scrollWheelSpeed: 1.0,          // how fast should the mouse wheel scroll. nagive values will revers the scroll direction (0:= deactivate mouse wheel)

        keys: {                         // key => function definition, if set to {} keys ar deactivated
            13: function () { this.conf.onclickActiveItem(this._activeItem) },
            37: function () { this.moveTo('pre') }, 
            38: function () { this.moveTo('visibleNext') },
            39: function () { this.moveTo('next') },
            40: function () { this.moveTo('visiblePre') }
        },

        reflectionColor: "transparent", // none, transparent, overlay or hex RGB CSS style #RRGGBB
        reflectionHeight: 0.5,          // float (relative to original image height)
        reflectionGap: 0.0,             // gap between the image and the reflection

        /*
         * ==================== helper and calculation methods ====================
         *
         * This section contains all user definable methods. With thees you can
         * change the behavior and the visual effects of the flow.
         * For an explanation of each method take a look at the documentation.
         *
         * BEWARE:  All methods are bond to the ContentFlow!!!
         *          This means that the keyword 'this' refers to the ContentFlow 
         *          which called the method.
         */
        
        /* ==================== actions ==================== */

        onmouseoverActiveItem: function (item, event, el) {

            var currentItemIndex = this._getIndexByPosition(this._currentPosition);
            var back = this.itemsback[currentItemIndex];
            if (back != null) {
                if (back.imageSide == 0) {

                    eX = event.clientX;
                    eY = event.clientY;
//                    console.log("over", eX, eY);

                    var conf = this.conf;
                    conf.startmouseover(eX, eY, el, back);

                }
            }
        
        },

        onmouseoutActiveItem: function (item, event, el) {

            var currentItemIndex = this._getIndexByPosition(this._currentPosition);
            var back = this.itemsback[currentItemIndex];
            if (back != null) {
                if (back.imageSide == 0) {

                    eX = event.clientX;
                    eY = event.clientY;
//                    console.log("out", eX, eY);

                    var conf = this.conf;
                    conf.endmouseover(eX, eY, el, back);

                }
            }
        
        },

        onmousemoveActiveItem: function (item, event, el) {

            var currentItemIndex = this._getIndexByPosition(this._currentPosition);
            var back = this.itemsback[currentItemIndex];
            if (back != null) {
                if (back.imageSide == 0) {

                    eX = event.clientX;
                    eY = event.clientY;
//                    console.log("move", eX, eY);

                    var conf = this.conf;
                    conf.mousemove(eX, eY, el, back);

                }
            }
        
        },

        startmouseover: function (mx, my, el, back) {

            var hovertrack = this.conf.checktrack(back, el, mx, my);
//            console.log("START: ",hovertrack);
            back.currenthovertrack = hovertrack;
            if (hovertrack != 0) {
                // add highlight to current hovertrack
                back.addhighlight(hovertrack);
                back.previoushovertrack = hovertrack;
            }

        },

        endmouseover: function (mx, my, el, back) {

//            console.log("END: ",back.currenthovertrack);
            if (back.currenthovertrack != 0) {
                // remove highlight from current hovertrack
                back.removehighlight(back.currenthovertrack);
                back.currenthovertrack = 0;
            }

        },

        mousemove: function (mx, my, el, back) {

            var hovertrack = this.conf.checktrack(back, el, mx, my);
//            console.log("MOVE: ",hovertrack);
            if (back.currenthovertrack != hovertrack) {
                if (back.currenthovertrack != 0) {
                    // remove highlight from old hovertrack
                    back.removehighlight(back.currenthovertrack);
                }
                back.currenthovertrack = hovertrack;
                if (back.currenthovertrack != 0) {
                    // add highlight to new hovertrack
                    back.addhighlight(back.currenthovertrack);
                }
            }
        },

        checktrack: function (back, el, mx, my) {

            // TODO: currently don't check X as we must be within the bounds of the cover and don't differentiate cover and text

            // TODO: need to scale this if we aren't on the currentItem

            var off = $(el).offset();
            var ox = off.left;
            var oy = off.top;
            var oh = $(el).height();
            var ow = $(el).width();

            trackcount = back.trackcount
            x1 = ox;
            x2 = ox + ow;
            y1 = oy;
            y2 = oy + oh;
            sonosconf = this.getAddOnConf('sonos');
            trackstartY = y1 + sonosconf.artistY + sonosconf.albumFontHeight + (sonosconf.albumGapHeight / 2) - 2;
            trackdepthY = sonosconf.albumFontHeight + sonosconf.albumGapHeight;
            trackendY = trackstartY + (trackcount * trackdepthY);
            if (my >= trackstartY && my <= trackendY) {
                dY = my - trackstartY;
                if (my == 0) my = 1;
                tracknum = Math.ceil(dY / trackdepthY);
                return tracknum;
            }
            else return 0;

        },

        processrightclick : function (option, content, x, y) {

//            console.log("processrightclick", option, content);

            currentindex = this._activeItem.getIndex();
            visibleitems = this.conf.visibleItems;
            range = (visibleitems * 2) + 1;
            numitems = this.itemsLastIndex + 1;

            if (numitems <= range) {
                n1 = 0;
                range = numitems - 1;
            }
            else {
                n1 = currentindex - visibleitems;
                if (n1 < 0) n1 = numitems + n1;
            }
            itemid = $(content).attr('id');
            var currentItemIndex = -1;
            var index = n1;
            for (var i = 0; i <= range-1; i++) {
                index += 1;
                if (index >= numitems) index = 0;

                var flowitem = this.items[index];
                var flowitemid = $(flowitem.content).attr('id');
                
                if (flowitemid == itemid) {
                    currentItemIndex = index;
                }
            }

            if (currentItemIndex != -1) {

                var back = this.itemsback[currentItemIndex];

                // check if we clicked on the front
                if (back == null || back.imageSide != 0) {
                    // if we clicked on the front, perform the action for the whole album            
//                    console.log("play whole album");
                    processmenuflow(option, content);
                }
                else {
                    // if tracks are selected, perform the action for them
                    var count = 0;
                    var trackentries = '';
                    for (var i = 0; i < back.tracks.length; i++) {
                        if (back.tracks[i].selectstatus > 0) {
//                            console.log("play track " + (i+1));
                            count += 1;
                            if (count != 1) trackentries += "::::";
                            trackentries += back.tracks[i].entry;
                        }
                    }
                    if (count != 0) processmenuflowmulti(option, count, trackentries);
                    else {
                        // no tracks selected - if a track is highlighted, play that, else play whole album
                        var clicktrack = this.conf.checktrack(back, content, x, y);
                        if (clicktrack != 0) {
                            var trackentries = back.tracks[clicktrack-1].entry;
                            processmenuflowmulti(option, 1, trackentries);
                        }
                        else {                        
                            processmenuflow(option, content);
                        }
                    }
                }
            }
            
        },

        /*
         * called after the inactive item is clicked.
         */
        onclickInactiveItem : function (item) {},

        /*
         * called after the active item is clicked.
         */
        onclickActiveItem: function (item, event, el) {

            console.log("h0");

            // TODO: this code needs fixing for IE

            var conf = this.conf;
            var currentItemIndex = item.getIndex();

            console.log("h0-1");

            if (this.itemsback[currentItemIndex] == null) {
                // no back for this item - create one
                caption = item.caption;
                this.itemsback[currentItemIndex] = new ContentFlowBack(this, currentItemIndex, caption);
            }
            var back = this.itemsback[currentItemIndex];

            console.log("h0-2");

            // check if we clicked a track on the back
            if (back.imageSide == 0) {

                eX = event.clientX;
                eY = event.clientY;
            
                var clicktrack = conf.checktrack(back, el, eX, eY);
                if (clicktrack != 0) {

                    // left click - play track
                    // shift/left click - select set of tracks
                    //     if first track selected, select track
                    //     if track already selected, select all tracks between those tracks (inclusive)
                    // ctrl/left click - toggle track
                    shiftPressed = event.shiftKey;
                    ctrlPressed  = event.ctrlKey;
                    if (shiftPressed) {
//                        console.log("TRACK SHIFT CLICKED: ", clicktrack);
                        // check for (last) track selected before this one
                        var trackfound = 0;
                        for (var i = 0; i < clicktrack-1; i++) {
                            if (back.tracks[i].selectstatus > 0) {
                                trackfound = i+1;
                            }
                        }
                        if (trackfound == 0) {
                            // check for (first) track selected after this one
                            for (var i = clicktrack; i < back.tracks.length; i++) {
                                if (back.tracks[i].selectstatus > 0) {
                                    if (trackfound == 0) trackfound = i+1;
                                }
                            }
                        }
                        if (trackfound != 0) {
                            n1 = Math.min(trackfound, clicktrack);
                            n2 = Math.max(trackfound, clicktrack);
                            for (var i = n1; i <= n2; i++) {
                                back.addselection(i);
                            }
                        }
                        else {
                            // no other tracks selected, just select this one
                            back.addselection(clicktrack);
                        }
                    }
                    else if (ctrlPressed) {
//                        console.log("TRACK CTRL CLICKED: ", clicktrack);
                        back.toggleselection(clicktrack);
                    }
                    else {
//                        console.log("TRACK CLICKED: ", clicktrack);
                        back.addselection(clicktrack);
                    }
                    
                    return;
                }
            }            
            
            console.log("h1");
            
            // TODO: which of the code below do we really need?
            var els = item.element.style;
            var size = conf.calcSize(item);
            size.height = Math.max(size.height, 0);
            size.width = Math.max(size.width, 0);
            if (item.content.origProportion) size = this._scaleImageSize(item, size);
            item.size = size;
            size.height *= this.maxHeight;
            size.width *= this.maxHeight;

            console.log("h2");

//            var coords = conf.calcCoordinates(item);
//            var pX = this.Flow.center.x * ( 1 + coords.x )  + (0 - 1)  * size.width/2;
//            var pY = this.maxHeight/2 * ( 1 + coords.y ) + (0 - 1 )* size.height/2;
            // *******************************************
            // TODO: note we've introduced jQuery here....
            // *******************************************
            var pX = $(el).offset().left;
            var pY = $(el).offset().top;
            
//            console.log(event, back, back.imageSide);
            
            iterations = 15;
            millisecondsPerFlip = 10;
            delta = Math.abs(size.width) / iterations;

            console.log("h3");


            var i=1;
            var c=1;
            var foobar = function () { 

                if (i == 1 && back.imageSide == -1) {
                    flowclick(item.content, currentItemIndex);
                }

                pX += delta / 2;

                size.width -= delta;
                if (Math.abs(size.width) < 0.01) size.width = 0.0;
                els.left = pX+"px";
                els.width = size.width +"px";
                els.visibility = "visible";
                els.display = "block";
                i += 1;
                if (i <= iterations) window.setTimeout(foobar, millisecondsPerFlip);
                else {
                    if (c == 1) {

                        back.swapImage(item);
                    
                        c=0;
                        i=1;
                        delta *= -1.0;
                        window.setTimeout(foobar, millisecondsPerFlip);
                    }
                }
            }.bind(this);

            window.setTimeout(foobar, millisecondsPerFlip);

        },

        /*
         * called when an item becomes inactive.
         */
        onMakeInactive: function (item) {
        
            var itemindex = item.getIndex();
            var back = this.itemsback[itemindex];
            if (back != null) {
                if (back.imageSide == 0) {
                    back.unhighlightall();
                }
            }
        
        },

        /*
         * called when an item becomes active.
         */
        onMakeActive: function (item) {},
        
        /*
         * called when the target item/position is reached
         */
        onReachTarget: function(item) {},

        /*
         * called when a new target is set
         */
        onMoveTo: function(item) {},

        /*
         * called each item an item is drawn (after scaling and positioning)
         */
        onDrawItem: function(item) {},

        /*
         * called if the pre-button is clicked.
         */
        onclickPreButton: function (event) {
            this.moveToIndex('pre');
            Event.stop(event);
        },
        
        /*
         * called if the next-button is clicked.
         */
        onclickNextButton: function (event) {
            this.moveToIndex('next');
            Event.stop(event);
        },
        
        /* ==================== calculations ==================== */

        /*
         * calculates the width of the step.
         */
        calcStepWidth: function(diff) {
            var vI = this.conf.visibleItems;
//            var items = this.items.length;
            var items = 30;
            items = items == 0 ? 1 : items;
            if (Math.abs(diff) > vI) {
                if (diff > 0) {
                    var stepwidth = diff - vI;
                } else {
                    var stepwidth = diff + vI;
                }
//            } else if (vI >= this.items.length) {
            } else if (vI >= 30) {
                var stepwidth = diff / items;
            } else {
                var stepwidth = diff * ( vI / items);
            }
            return stepwidth;
        },
        

        /*
         * calculates the size of the item at its relative position x
         *
         * relativePosition: Math.round(Position(activeItem)) - Position(item)
         * side: -1, 0, 1 :: Position(item)/Math.abs(Position(item)) or 0 
         * returns a size object
         */
        calcSize: function (item) {
            var rP = item.relativePosition;

            var h = 1/(Math.abs(rP)+1);
            var w = h;
            return {width: w, height: h};
        },

        /*
         * calculates the position of an item within the flow depending on it's relative position
         *
         * relativePosition: Math.round(Position(activeItem)) - Position(item)
         * side: -1, 0, 1 :: Position(item)/Math.abs(Position(item)) or 0 
         */
        calcCoordinates: function (item) {
            var rP = item.relativePosition;
            //var rPN = item.relativePositionNormed;
            var vI = this.conf.visibleItems; 

            var f = 1 - 1/Math.exp( Math.abs(rP)*0.75);
            var x =  item.side * vI/(vI+1)* f; 
            var y = 1;

            return {x: x, y: y};
        },
        
        /*
         * calculates the position of an item relative to it's calculated coordinates
         * x,y = 0 ==> center of item has the position calculated by
         * calculateCoordinates
         *
         * relativePosition: Math.round(Position(activeItem)) - Position(item)
         * side: -1, 0, 1 :: Position(item)/Math.abs(Position(item)) or 0 
         * size: size object calculated by calcSize
         */
        calcRelativeItemPosition: function (item) {
            var x = 0;
            var y = -1;
            return {x: x, y: y};
        },

        /*
         * calculates and returns the relative z-index of an item
         */
        calcZIndex: function (item) {
            return -Math.abs(item.relativePositionNormed);
        },

        /*
         * calculates and returns the relative font-size of an item
         */
        calcFontSize: function (item) {
//            return item.size;
            return 1;       // fix issue getting font-size (note in contentflow_src.js the above line is "return item.size.height;"
        },

        /*
         * calculates and returns the opacity of an item
         */
        calcOpacity: function (item) {
            return Math.max(1 - ((1 - this.conf.endOpacity ) * Math.sqrt(Math.abs(item.relativePositionNormed))), this.conf.endOpacity);
        }
	
    }

});

/* 
 * ============================================================
 * ContentFlowBack
 * ============================================================
 */
var ContentFlowBack = function (flow, index, caption) {

    console.log("c0");

    this.currenthovertrack = 0;

    this.sonosconf = flow.getAddOnConf('sonos');

    this.flow = flow;
    var item = flow.items[index];
    console.log("c1");
    var context = item.content.getContext("2d");
    console.log("c2");

    width = this.width = item.content.width;
    height = this.height = item.content.height;

    tempImageData = context.getImageData(0, 0, width, height);
    item.content.width = width;  // seems we have to re-set this for drawImage to work properly
    item.content.height = height;    // and this
    context.save();
    // TODO: only add if set
    this.addReflection(flow, item.origContent, item);
    context.translate(width, 0);
    context.scale(-1, 1);
    context.globalAlpha = 0.2;
    context.drawImage(item.origContent, 0, 0, width, height);
    this.backImageData = context.getImageData(0, 0, width, height);
    context.restore();
    context.putImageData(tempImageData, 0, 0);

    this.imageSide = -1;     // -1 = front with back never visited, 1 = front, 0 = back
    this.trackscomplete = false;
    this.album = caption.childNodes[0].textContent;
    this.artist = caption.childNodes[2].textContent;

    this.context = context; // TODO: is this safe?
    
    this.writeBackTitle = function (context) {
        context.fillStyle    = '#FFFFFF';
        context.font         = '12px sans-serif';
        context.textBaseline = 'top';
        out = "Album: " + this.album;
        context.fillText(out, this.sonosconf.albumX, this.sonosconf.albumY);
        out = "Artist: " + this.artist;
        context.fillText(out, this.sonosconf.artistX, this.sonosconf.artistY);
    };

    this.writeBackTracks = function (context) {
        context.fillStyle    = '#66CCFF';
        context.font         = this.sonosconf.albumFont;
        context.textBaseline = 'top';
        x = this.sonosconf.leftGapWidth;
        y = this.sonosconf.artistY + this.sonosconf.albumFontHeight + (this.sonosconf.albumGapHeight / 2);
        d = this.sonosconf.albumFontHeight + this.sonosconf.albumGapHeight;
        for (var i = 0; i < this.tracks.length; i++) {
            out = (i+1) + ". " + this.tracks[i].text;
            context.fillText(out, x, y);
            y += d;
        }
    };

    this.unhighlightall = function () {
        var context = this.context;
        context.fillStyle    = '#66CCFF';
        context.font         = this.sonosconf.albumFont;
        context.textBaseline = 'top';
        x = this.sonosconf.leftGapWidth;
        y = this.sonosconf.artistY + this.sonosconf.albumFontHeight + (this.sonosconf.albumGapHeight / 2);
        d = this.sonosconf.albumFontHeight + this.sonosconf.albumGapHeight;
        for (var i = 0; i < this.tracks.length; i++) {
            if (this.tracks[i].imagedata != null && this.tracks[i].selectstatus > 0) {
                this.settrackimage(context, i+1);
                this.tracks[i].selectstatus = 0;
            }
            y += d;
        }
    };

    this.writesinglebacktrack = function (context, colour, track) {
        context.fillStyle    = colour;
        context.font         = this.sonosconf.albumFont;
        context.textBaseline = 'top';
        out = track + ". " + this.tracks[track-1].text;
        pos = this.gettracklocation(track);
        context.fillText(out, pos.x, pos.y + 1);
    };

    this.writesinglebackhighlight = function (context, colour, track) {
        context.fillStyle    = colour;
        pos = this.gettracklocation(track);
        width = this.width;
        height = this.sonosconf.albumFontHeight + this.sonosconf.albumGapHeight;
        context.fillRect(pos.x, pos.y-1, width, height);
    };

    this.gettrackimage = function (context, track) {
        if (this.tracks[track-1].imagedata != null) return;
        pos = this.gethighlightlocation(track);
        width = this.width;
        height = this.sonosconf.albumFontHeight + this.sonosconf.albumGapHeight;
        this.tracks[track-1].imagedata = context.getImageData(pos.x, pos.y-1, width, height);
    };

    this.settrackimage = function (context, track) {
        pos = this.gethighlightlocation(track);
        context.putImageData(this.tracks[track-1].imagedata, pos.x, pos.y-1);
    };

    this.gettracklocation = function (track) {
        x = this.sonosconf.leftGapWidth;
        y = this.sonosconf.artistY + this.sonosconf.albumFontHeight + (this.sonosconf.albumGapHeight / 2) - 1;
        d = this.sonosconf.albumFontHeight + this.sonosconf.albumGapHeight;
        yout = y + ((track-1) * d);
        return {x:x, y:yout}           
    };

    this.gethighlightlocation = function (track) {
        pos = this.gettracklocation(track);
        pos.x -= this.sonosconf.leftGapWidth;
        return pos
    };

    this.addhighlight = function (track) {
        var context = this.context;
        if (this.tracks[track-1].selectstatus == 0) this.tracks[track-1].selectstatus = 1;
        this.gettrackimage(context, track);
        this.writesinglebackhighlight(context, '#FFFFFF', track);
        this.writesinglebacktrack(context, '#66CCFF', track);
    };

    this.removehighlight = function (track) {
        var context = this.context;
        this.settrackimage(context, track);
        if (this.tracks[track-1].selectstatus == 2) {
            this.addselection(track);
        }
        else this.tracks[track-1].selectstatus = 0;
    };

    this.addselection = function (track) {
        var context = this.context;
        this.tracks[track-1].selectstatus = 2;
        this.gettrackimage(context, track);
        this.writesinglebackhighlight(context, '#2779aa', track);
        this.writesinglebacktrack(context, '#66CCFF', track);
    };

    this.removeselection = function (track) {
        this.tracks[track-1].selectstatus = 0;
        var context = this.context;
        this.settrackimage(context, track);
    };

    this.toggleselection = function (track) {
        if (this.tracks[track-1].selectstatus == 2) this.removeselection(track);
        else this.addselection(track);
    };

    // swap the image on screen with the image saved as the back
    this.swapImage = function (item) {

        width = item.content.width;
        height = item.content.height;

        var context = item.content.getContext("2d");
        tempImageData = context.getImageData(0, 0, width, height);
        item.content.width = width;
        item.content.height = height; 
        context.putImageData(this.backImageData, 0, 0);
        this.backImageData = tempImageData;

        if (this.imageSide == -1) {
            this.writeBackTitle(context);
            // write tracks if they are complete (they won't have been written as back was not displayed)
            if (this.trackscomplete == true) this.writeBackTracks(context);
            this.imageSide = 0;
        }
        else {
            this.imageSide = this.imageSide == 1 ? 0 : 1;
        }
    };

    this.updateback = function (index, tracklist) {

//        console.log("updateback", index, tracklist);

        this.tracks = new Array();
        var as = tracklist.getElementsByTagName('a');
        this.trackcount = as.length;
        var imagedata = null;
        var selectstatus = null;
        for (var i = 0; i < as.length; i++) {
            var t = as[i];
//<a type="T" menu="ZP_LIBRARY_PLAY" id="atarget5_3_3_1"><span style="float: left;"></span><img src="/sonospy/static/note.png">Come to Me</a>
            var text = this.gettext(t);
            var id = t.getAttribute('id').substring(7);
            var type = t.getAttribute('type');
            var menu = t.getAttribute('menu');
            var entry = id + '::' + type + '::' + menu + '::' + text
            this.tracks.push({text:text, id:id, entry:entry, element:t, data:imagedata, selectstatus:selectstatus});
        }


        this.trackscomplete = true;

        if (this.imageSide == 0) {
            this.writeBackTracks(this.context);
        }
/*
<ul id="navigation" type="none">

    <li tree="closed" class="play">
        <span type="T">
            <a id="atarget5_3_3_1" menu="ZP_LIBRARY_PLAY" type="T">
                <span style="float: left;"></span>
                <img src="/sonospy/static/note.png">Come to Me
            </a>
        </span>
        <span id="starget5_3_3_1"></span>
        <span id="target5_3_3_1"></span>
    </li>

    <li tree="closed" class="play"><span type="T"><a id="atarget5_3_3_2" menu="ZP_LIBRARY_PLAY" type="T"><span style="float: left;"></span><img src="/sonospy/static/note.png">Lovefool</a></span><span id="starget5_3_3_2"></span><span id="target5_3_3_2"></span></li>
    <li tree="closed" class="play"><span type="T"><a id="atarget5_3_3_3" menu="ZP_LIBRARY_PLAY" type="T"><span style="float: left;"></span><img src="/sonospy/static/note.png">Lovefool [Tee's Club Radio]</a></span><span id="starget5_3_3_3"></span><span id="target5_3_3_3"></span></li>
    <li tree="closed" class="play"><span type="T"><a id="atarget5_3_3_4" menu="ZP_LIBRARY_PLAY" type="T"><span style="float: left;"></span><img src="/sonospy/static/note.png">The Clansman</a></span><span id="starget5_3_3_4"></span><span id="target5_3_3_4"></span></li>
    <li tree="closed" class="play"><span type="T"><a id="atarget5_3_3_5" menu="ZP_LIBRARY_PLAY" type="T"><span style="float: left;"></span><img src="/sonospy/static/note.png">Can't Fight The Moonlight (Latino mix) - LeAnn Rimes</a></span><span id="starget5_3_3_5"></span><span id="target5_3_3_5"></span></li>
    <li tree="closed" class="play"><span type="T"><a id="atarget5_3_3_6" menu="ZP_LIBRARY_PLAY" type="T"><span style="float: left;"></span><img src="/sonospy/static/note.png">Life Goes On</a></span><span id="starget5_3_3_6"></span><span id="target5_3_3_6"></span></li>
    <li tree="closed" class="play"><span type="T"><a id="atarget5_3_3_7" menu="ZP_LIBRARY_PLAY" type="T"><span style="float: left;"></span><img src="/sonospy/static/note.png">There You'll Be</a></span><span id="starget5_3_3_7"></span><span id="target5_3_3_7"></span></li>
    <li tree="closed" class="play"><span type="T"><a id="atarget5_3_3_8" menu="ZP_LIBRARY_PLAY" type="T"><span style="float: left;"></span><img src="/sonospy/static/note.png">Move Your Feet</a></span><span id="starget5_3_3_8"></span><span id="target5_3_3_8"></span></li>
    <li tree="closed" class="play"><span type="T"><a id="atarget5_3_3_9" menu="ZP_LIBRARY_PLAY" type="T"><span style="float: left;"></span><img src="/sonospy/static/note.png">Addicted</a></span><span id="starget5_3_3_9"></span><span id="target5_3_3_9"></span></li>
    <li tree="closed" class="play"><span type="T"><a id="atarget5_3_3_10" menu="ZP_LIBRARY_PLAY" type="T"><span style="float: left;"></span><img src="/sonospy/static/note.png">Work It</a></span><span id="starget5_3_3_10"></span><span id="target5_3_3_10"></span></li>
    <li tree="closed" class="play"><span type="T"><a id="atarget5_3_3_11" menu="ZP_LIBRARY_PLAY" type="T"><span style="float: left;"></span><img src="/sonospy/static/note.png">Addicted To Bass - Puretone</a></span><span id="starget5_3_3_11"></span><span id="target5_3_3_11"></span></li>
</ul>
*/

    };

    this.gettext = function (node) {
        var text = ''
        for (var i=0; i<node.childNodes.length; i++) {
            var c = node.childNodes[i];
            if (c.nodeType == 3) text += c.nodeValue;
        }
        return text;
    };

};

ContentFlowBack.prototype = {
    
    /*
     * add reflection to item
     */
    addReflection: function(flow, content, item) {
        var CFobj = flow;
        var reflection;
        var image = content;


        // TODO: check IE code for necessary updates OR merge orig src and this

        if (flow.Browser.IE) {
            var filterString = 'progid:DXImageTransform.Microsoft.BasicImage(rotation=2, mirror=1)';
            if (CFobj._reflectionColorRGB) {
                // transparent gradient
                if (CFobj.conf.reflectionColor == "transparent") {
                    var RefImg = reflection = this.reflection = document.createElement('img');
                    reflection.src = image.src;
                }
                // color gradient
                else {
                    reflection = this.reflection = document.createElement('div');
                    var RefImg = document.createElement('img');
                    RefImg.src = image.src;
                    reflection.width = RefImg.width;
                    reflection.height = RefImg.height;
                    RefImg.style.width = '100%';
                    RefImg.style.height = '100%';
                    var color = CFobj._reflectionColorRGB;
                    reflection.style.backgroundColor = '#'+color.hR+color.hG+color.hB;
                    reflection.appendChild(RefImg);
                }
                filterString += ' progid:DXImageTransform.Microsoft.Alpha(opacity=0, finishOpacity=50, style=1, finishX=0, startY='+CFobj.conf.reflectionHeight*100+' finishY=0)';
            } else {
                var RefImg = reflection = this.reflection = document.createElement('img');
                reflection.src = image.src;
            }
            // crop image (streches and crops (clip on default dimensions), original proportions will be restored through CSS)
            filterString += ' progid:DXImageTransform.Microsoft.Matrix(M11=1, M12=0, M21=0, M22='+1/CFobj.conf.reflectionHeight+')';

            if (ContentFlowGlobal.Browser.IE6) {
                if (image.src.match(/\.png$/) ) {
                    image.style.filter = "progid:DXImageTransform.Microsoft.AlphaImageLoader(src='"+image.src+"', sizingMethod=scale )";
                    image.filterString = "progid:DXImageTransform.Microsoft.AlphaImageLoader(src='"+image.src+"', sizingMethod=scale )";
                    filterString += " progid:DXImageTransform.Microsoft.AlphaImageLoader(src='"+image.src+"', sizingMethod=scale )";
                    image.origSrc = image.src;
                    image.src='img/blank.gif';
                    RefImg.src="img/blank.gif";
                }
            }

            reflection.filterString = filterString;
            RefImg.style.filter = filterString;

        } else {
            if (CFobj._reflectionWithinImage)
                var canvas = this.canvas = $CF(document.createElement('canvas'));
            else 
                var canvas = reflection = this.reflection = document.createElement('canvas');

            if (canvas.getContext) {
                if (CFobj._reflectionWithinImage) {
                    for (var i=0; i <image.attributes.length; i++) {
                        canvas.setAttributeNode(image.attributes[i].cloneNode(true));
                    }
                }

                var context = canvas.getContext("2d");

                /* calc image size */
                var max = CFobj.maxHeight;
                var size = CFobj._scaleImageSize(item, {width: max, height: max }, max)
                var width = size.width;
                var height = size.height;

                // overwrite default height and width
                if (CFobj._reflectionWithinImage) {
                    canvas.width = width;
                    canvas.height = height; 
                    item.setImageFormat(canvas);
                    canvas.height = height * (1 + CFobj.conf.reflectionHeight + CFobj.conf.reflectionGap);

                }
                else {
                    canvas.width = width;
                    canvas.height = height * CFobj.conf.reflectionHeight;
                }
                    
                context.save(); /* save default context */

                /* draw image into canvas */
                if (CFobj._reflectionWithinImage) {
                    context.drawImage(image, 0, 0, width, height);
                }

                /* mirror image by transformation of context and image drawing */
                if (CFobj._reflectionWithinImage) {
                    var contextHeight = height * ( 1 + CFobj.conf.reflectionGap/2) * 2;
                }
                else {
                    var contextHeight = image.height;
                }
                // -1 for FF 1.5
                contextHeight -= 1;
                
                context.translate(0, contextHeight);
                context.scale(1, -1);
                /* draw reflection image into canvas */
                context.drawImage(image, 0, 0, width, height);

                /* restore default context for simpler further canvas manupulation */
                context.restore();
                    
                if (CFobj._reflectionColorRGB) {
                    var gradient = context.createLinearGradient(0, 0, 0, canvas.height);

                    var alpha = [0, 0.5, 1];
                    if (CFobj._reflectionColor == "transparent") {
                        context.globalCompositeOperation = "destination-in";
                        alpha = [1, 0.5, 0];
                    }

                    var red = CFobj._reflectionColorRGB.iR;
                    var green = CFobj._reflectionColorRGB.iG;
                    var blue = CFobj._reflectionColorRGB.iB;
                    if (CFobj._reflectionWithinImage) {
                        gradient.addColorStop(0, 'rgba('+red+','+green+','+blue+','+alpha[0]+')');
                        gradient.addColorStop(height/canvas.height, 'rgba('+red+','+green+','+blue+','+alpha[0]+')');
                        gradient.addColorStop(height/canvas.height, 'rgba('+red+','+green+','+blue+','+alpha[1]+')');
                    }
                    else {
                        gradient.addColorStop(0, 'rgba('+red+','+green+','+blue+','+alpha[1]+')');
                    }
                    gradient.addColorStop(1, 'rgba('+red+','+green+','+blue+','+alpha[2]+')');

                    context.fillStyle = gradient;
                    context.fillRect(0, 0, canvas.width, canvas.height);
                    
                }

                if (CFobj._reflectionWithinImage) {
//                    image.parentNode.replaceChild(canvas, image);
                    item.origContent = canvas;
//                    this.origContent = image;
                    delete this.image;// = true;

                }
                
            } else {
                CFobj._reflectionWithinImage = false;
                delete this.reflection;
            }

        }
        if (reflection) {
            reflection.className = "reflection";
            this.element.appendChild(reflection);

            /* be shure that caption is last child */
            if (this.caption) this.element.appendChild(this.caption);
        } 

    }
    
};

