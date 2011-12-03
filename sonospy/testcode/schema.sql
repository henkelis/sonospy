      tags                  (title, album, artist, track, path, filename)
              id
              id2
              title  
              artist 
              album 
              genre 
              track 
              year 
              albumartist 
              composer 
              codec 
              length 
              size 
              lastmodified 
              path 
              filename 
              discnumber 
              comment 
              cover 
              bitrate 
              samplerate
              bitspersample
              channels
              mime 
              lastupdated 
              upnpclass 
              scannumber
              artid
              inserted
              lastscanned

      tracks                (title, album, artist, tracknumber)
              id
              id2
              parentID
              duplicate  
              title
              artist
              album 
              genre
              tracknumber
              year 
              albumartist
              composer
              codec 
              tag
              length
              size 
              lastmodified
              path
              filename 
              discnumber
              comment
              cover 
              bitrate
              samplerate
              bitspersample
              channels
              mime 
              res
              protocol
              lastupdated
              upnpclass 
              artid
              inserted
              lastscanned

      albums                (album, artist, albumartist, duplicate)
              id  
              parentID  
              album  
              artist 
              year 
              albumartist  
              duplicate  
              cover 
              artid
              inserted
              lastplayed
              playcount
              upnpclass 

      artists               (artist, albumartist)
              id 
              parentID  
              artist 
              albumartist  
              lastplayed
              playcount
              upnpclass 

      composers             (composer)
              id 
              parentID  
              composer 
              upnpclass 

      genres                (genre)
              id 
              parentID  
              genre 
              upnpclass 

      playlists             (playlist)
              id 
              parentID  
              playlist 
              path 
              upnpclass 

      GenreArtist           (artist_id, genre)
      
              artist_id 
              genre
              
      GenreAlbumartist      (albumartist_id, genre)
      
              albumartist_id 
              genre
              
      GenreArtistAlbum      (album_id, genre, artist, album)
      
              album_id 
              genre
              artist
              album
              duplicate
              
      GenreAlbumartistAlbum (album_id, genre, albumartist, album)
      
              album_id 
              genre
              albumartist
              album
              duplicate
              
      ArtistAlbum           (album_id, artist, album)
      
              album_id 
              artist
              album
              duplicate
              
      AlbumartistAlbum      (album_id, albumartist, album)
      
              album_id 
              albumartist
              album
              duplicate
              
      ComposerAlbum         (album_id, composer, album)
      
              album_id 
              composer
              album
              duplicate
              
      GenreArtistAlbumTrack (track_id, genre, artist, album)
      
              track_id 
              genre
              artist
              album
              duplicate
              
      GenreAlbumartistAlbumTrack    (track_id, genre, albumartist, album)
      
              track_id 
              genre
              albumartist
              album
              duplicate
              
      ArtistAlbumTrack      (track_id, artist, album)
      
              track_id 
              artist
              album
              duplicate
              
      AlbumartistAlbumTrack (track_id, albumartist, album)
      
              track_id 
              albumartist
              album
              duplicate
              
      ComposerAlbumTrack    (track_id, composer, album)
      
              track_id 
              composer
              album
              duplicate

