/*  ContentFlowAddOn_gallery, version 3.0 
 *  (c) 2008 - 2010 Sebastian Kutsch
 *  <http://www.jacksasylum.eu/ContentFlow/>
 *
 *  This file is distributed under the terms of the MIT license.
 *  (see http://www.jacksasylum.eu/ContentFlow/LICENSE)
 */

new ContentFlowAddOn ('gallery', {

	ContentFlowConf: {
        maxItemHeight: 0,
        visibleItems: 4,
        relativeItemPosition: "top center",

        calcSize: function ( item) {
            var rP = item.relativePosition;
            //var rPN = relativePositionNormed;
            //var vI = rPN != 0 ? rP/rPN : 0 ; visible Items

            var h = 0.9;

            var s = 0.2;
            var dH = 1.5;
            h *= (Math.normDist(rP,s)+dH)/(Math.normDist(0,s)+dH);
            
            var w = h;

            return {width: w, height: h};
        },

        calcCoordinates: function (item) {
            var rP = item.relativePosition;
            var rPN = item.relativePositionNormed;
            var vI = rPN != 0 ? rP/rPN : 0 ; // visible Items

            var z  = item.side * (1 - Math.normedNormDist(rP, 0.5))/4; // runs from -0.25 ... 0 ... 0.25 
            var f = Math.sqrt(Math.erf2(rP)) *1.1;

            var x =  rP/(vI+1) * f + z; // normalized to (vI+1)
            var y = 1;

            return {x: x, y: y};
        }

	}

});
