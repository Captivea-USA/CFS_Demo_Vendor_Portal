/* Copyright (c) 2015-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>) */
/* See LICENSE file for full copyright and licensing details. */
/* License URL : <https://store.webkul.com/license.html/> */
odoo.define('odoo_vendor_portal.take_price', function (require) {
    'use strict';

    require('web.dom_ready');
    var ajax = require('web.ajax');

    $('#wksubmit').on("click", function (event) {
        var offerPirce = $("#inputPrice").val();
        var offerDate = $("#inputDelivery").val();
        var offerNote = $("#inputNote").val();
        var today = new Date();
        today.setHours(0, 0, 0, 0)
        var offerDate1 = new Date(offerDate);
        offerDate1.setHours(0, 0, 0, 0)
        if (offerPirce !== "" && $.isNumeric(offerPirce) && offerDate !== "") {
            if (offerDate1 < today) {
                alert("The  date can\'t be in the past.");
            } else {
                var userId = parseInt($('#loguser').val());
                var rfqId = parseInt($('#rfqId').val());
                ajax.jsonRpc("/update/vendorprice/", 'call', {
                    'rfqId': rfqId,
                    'offerPrice': offerPirce,
                    'offerDate': offerDate,
                    'offerNote': offerNote,
                    'vendorUserId': userId
                })
                .then(function (vals) {
                    window.location.reload();
                });
            }
        } else {
            alert("Please enter valid details!!");
        }
    });
});
