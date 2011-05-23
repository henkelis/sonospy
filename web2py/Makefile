clean:
	rm -f httpserver.log 
	rm -f parameters*.py 
	rm -f -r applications/*/compiled     	
	find ./ -name '*~' -exec rm -f {} \; 
	find ./ -name '#*' -exec rm -f {} \;
	find ./ -name 'Thumbs.db' -exec rm -f {} \; 
	find ./gluon/ -name '.*' -exec rm -f {} \;
	find ./gluon/ -name '*class' -exec rm -f {} \; 
	find ./applications/admin/ -name '.*' -exec rm -f {} \; 
	find ./applications/examples/ -name '.*' -exec rm -f {} \; 
	find ./applications/welcome/ -name '.*' -exec rm -f {} \; 
	find ./ -name '*.pyc' -exec rm -f {} \;
all:
	echo "The Makefile is used to build the distribution."
	echo "In order to run web2py you do not need to make anything."
	echo "just run web2py.py"
epydoc:
	### build epydoc
	rm -f -r applications/examples/static/epydoc/ 
	epydoc --config epydoc.conf
	cp applications/examples/static/title.png applications/examples/static/epydoc
src:
	echo 'Version 1.76.3 ('`date +%Y-%m-%d\ %H:%M:%S`')' > VERSION
	### rm -f all junk files
	make clean
	### clean up baisc apps
	rm -f routes.py 
	rm -f applications/*/sessions/*       
	rm -f applications/*/errors/* | echo 'too many files'
	rm -f applications/*/cache/*                  
	rm -f applications/admin/databases/*                 
	rm -f applications/welcome/databases/*               
	rm -f applications/examples/databases/*             
	rm -f applications/admin/uploads/*                 
	rm -f applications/welcome/uploads/*               
	rm -f applications/examples/uploads/*             
	### make admin layout and appadmin the default
	cp applications/admin/views/appadmin.html applications/welcome/views
	cp applications/admin/views/appadmin.html applications/examples/views
	cp applications/admin/controllers/appadmin.py applications/welcome/controllers
	cp applications/admin/controllers/appadmin.py applications/examples/controllers	
	### update the license
	cp ABOUT applications/admin/
	cp ABOUT applications/examples/
	cp LICENSE applications/admin/
	cp LICENSE applications/examples/
	### build web2py_src.zip
	echo '' > NEWINSTALL
	mv web2py_src.zip web2py_src_old.zip | echo 'no old'
	cd ..; zip -r web2py/web2py_src.zip web2py/gluon/*.py web2py/gluon/contrib/* web2py/*.py web2py/ABOUT  web2py/LICENSE web2py/README web2py/NEWINSTALL web2py/VERSION web2py/Makefile web2py/epydoc.css web2py/epydoc.conf web2py/app.yaml web2py/queue.yaml web2py/scripts/*.sh web2py/scripts/*.py web2py/applications/admin web2py/applications/examples/ web2py/applications/welcome web2py/applicaitons/__init__.py

mdp:
	make epydoc
	make src
	make app
	make win
app:
	python2.5 -c 'import compileall; compileall.compile_dir("gluon/")'
	#python web2py.py -S welcome -R __exit__.py
	find gluon -path '*.pyc' -exec cp {} ../web2py_osx/site-packages/{} \;
	cd ../web2py_osx/site-packages/; zip -r ../site-packages.zip *
	mv ../web2py_osx/site-packages.zip ../web2py_osx/web2py/web2py.app/Contents/Resources/lib/python2.5
	cp ABOUT ../web2py_osx/web2py/web2py.app/Contents/Resources
	cp NEWINSTALL ../web2py_osx/web2py/web2py.app/Contents/Resources
	cp LICENSE ../web2py_osx/web2py/web2py.app/Contents/Resources
	cp VERSION ../web2py_osx/web2py/web2py.app/Contents/Resources
	cp README ../web2py_osx/web2py/web2py.app/Contents/Resources
	cp -r applications/admin ../web2py_osx/web2py/web2py.app/Contents/Resources/applications
	cp -r applications/welcome ../web2py_osx/web2py/web2py.app/Contents/Resources/applications
	cp -r applications/examples ../web2py_osx/web2py/web2py.app/Contents/Resources/applications
	cp applications/__init__.py ../web2py_osx/web2py/web2py.app/Contents/Resources/applications
	cd ../web2py_osx; zip -r web2py_osx.zip web2py
	mv ../web2py_osx/web2py_osx.zip .
win:
	python2.5 -c 'import compileall; compileall.compile_dir("gluon/")'
	find gluon -path '*.pyc' -exec cp {} ../web2py_win/library/{} \;
	cd ../web2py_win/library/; zip -r ../library.zip *
	mv ../web2py_win/library.zip ../web2py_win/web2py
	cp ABOUT ../web2py_win/web2py/
	cp NEWINSTALL ../web2py_win/web2py/
	cp LICENSE ../web2py_win/web2py/
	cp VERSION ../web2py_win/web2py/
	cp README ../web2py_win/web2py/
	cp -r applications/admin ../web2py_win/web2py/applications
	cp -r applications/welcome ../web2py_win/web2py/applications
	cp -r applications/examples ../web2py_win/web2py/applications
	cp applications/__init__.py ../web2py_win/web2py/applications
	cd ../web2py_win; zip -r web2py_win.zip web2py
	mv ../web2py_win/web2py_win.zip .
run:
	python2.5 web2py.py -a hello
push:
	make clean
	echo '' > NEWINSTALL
	hg push
	bzr push bzr+ssh://mdipierro@bazaar.launchpad.net/~mdipierro/web2py/devel --use-existing-dir
post:
	scp -i ~/web2py.pem web2py_src.zip ubuntu@www.web2py.com:~/
	scp -i ~/web2py.pem web2py_win.zip ubuntu@www.web2py.com:~/
	scp -i ~/web2py.pem web2py_osx.zip ubuntu@www.web2py.com:~/

