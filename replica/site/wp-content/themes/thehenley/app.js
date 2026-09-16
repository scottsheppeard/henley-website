jQuery(function($) {


    // Scrolled

    $(window).scroll(function() {
	
        if ($(this).scrollTop() > 1) {
            $('body').addClass("scrolled");
        } else {
            $('body').removeClass("scrolled");
        }
        
    });



	// Mobile Menu

    $('.rk-mobile-menu .sub-menu').slideUp();

    $('.rk-menu-toggle').click(function(){
        $('body').toggleClass('rk-menu-open');
    });

    $('.rk-mobile-menu ul .menu-item-has-children > .toggle-icon').click(function(e){
        $(this).siblings('.sub-menu').slideToggle();
        $(this).toggleClass('flip');
    });


    // Hidden FAQ section

    $('#faq-section').slideUp();

    $('#faq-section-toggle').click(function(e) {
        e.preventDefault();
        $('#faq-section').slideToggle();
    })


});